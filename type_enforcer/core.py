"""Основной модуль Type Enforcer."""

import ast
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set, Union
from dataclasses import dataclass, field

from .config import Config, DEFAULT_IMPORTS


class ParentNodeTransformer(ast.NodeTransformer):
    """Трансформер для добавления ссылок на родительские узлы."""

    def visit(self, node):
        """Посетить узел и добавить ссылку на родителя для детей."""
        for child in ast.iter_child_nodes(node):
            setattr(child, 'parent', node)
        return super().visit(node)


@dataclass
class TypeViolation:
    """Нарушение использования типа."""

    file_path: str
    line: int
    column: int
    custom_type: str  # Кастомный тип, который должен использоваться
    standard_type: str  # Стандартный тип, который используется сейчас
    line_content: str
    context: str = ""

    def __str__(self) -> str:
        # Меняем сообщение, чтобы было понятно, что нужно использовать кастомный тип
        return f"{self.file_path}:{self.line}:{self.column} - Используйте кастомный тип '{self.custom_type}' вместо стандартного '{self.standard_type}'"

    @property
    def location(self) -> str:
        """Получить локацию в формате для IDE."""
        return f"{self.file_path}:{self.line}:{self.column}"


class TypeEnforcer:
    """Основной класс для проверки использования типов."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.default()
        self.violations: List[TypeViolation] = []

        # Создаем обратный словарь: стандартный тип -> кастомный тип
        # Используем только первый найденный кастомный тип для каждого стандартного
        self.standard_to_custom = {}
        for custom_type, standard_type in self.config.custom_types.items():
            if standard_type not in self.standard_to_custom:
                self.standard_to_custom[standard_type] = custom_type

    def scan_file(self, file_path: Union[str, Path]) -> List[TypeViolation]:
        """Сканировать один файл на нарушения."""
        file_path = Path(file_path)
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            # Добавляем ссылки на родительские узлы
            transformer = ParentNodeTransformer()
            transformer.visit(tree)

            lines = content.splitlines()

            # Найти все узлы, где используются имена типов
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self._check_name_node(node, file_path, lines, violations)
                elif isinstance(node, ast.AnnAssign) and node.annotation:
                    # Аннотации типов
                    self._check_annotation(node.annotation, file_path, lines, violations)
                elif isinstance(node, ast.FunctionDef):
                    # Возвращаемые типы функций
                    if node.returns:
                        self._check_annotation(node.returns, file_path, lines, violations)

                    # Аргументы функций
                    for arg in node.args.args:
                        if arg.annotation:
                            self._check_annotation(arg.annotation, file_path, lines, violations)

                    # Аргументы с дефолтными значениями (kwarg, vararg и т.д.)
                    if node.args.kwarg and node.args.kwarg.annotation:
                        self._check_annotation(node.args.kwarg.annotation, file_path, lines, violations)
                    if node.args.vararg and node.args.vararg.annotation:
                        self._check_annotation(node.args.vararg.annotation, file_path, lines, violations)

                    # Аргументы с дефолтными значениями
                    for arg in node.args.kwonlyargs:
                        if arg.annotation:
                            self._check_annotation(arg.annotation, file_path, lines, violations)

                elif isinstance(node, ast.Assign):
                    # Проверяем аннотации типов в присваиваниях (если есть)
                    if hasattr(node, 'type_comment') and node.type_comment:
                        # TODO: обработать type comments
                        pass

        except SyntaxError as e:
            print(f"Синтаксическая ошибка в файле {file_path}: {e}")
        except Exception as e:
            print(f"Ошибка при сканировании {file_path}: {e}")

        self.violations = violations
        return violations

    def _check_name_node(self, node: ast.Name, file_path: Path,
                         lines: List[str], violations: List[TypeViolation]):
        """Проверить узел с именем."""
        # Проверяем, является ли имя стандартным типом, который нужно заменить
        if node.id in self.standard_to_custom:
            # Проверяем, находится ли узел в контексте, где он действительно является типом
            if self._is_type_annotation(node):
                line_content = lines[node.lineno - 1].strip()
                # Проверяем, чтобы не добавлять дубликаты
                violation = TypeViolation(
                    file_path=str(file_path),
                    line=node.lineno,
                    column=node.col_offset,
                    custom_type=self.standard_to_custom[node.id],
                    standard_type=node.id,
                    line_content=line_content,
                    context=self._get_context(lines, node.lineno)
                )

                # Проверяем, чтобы не добавлять дубликаты
                if not self._violation_exists(violations, violation):
                    violations.append(violation)

    def _violation_exists(self, violations: List[TypeViolation], new_violation: TypeViolation) -> bool:
        """Проверить, существует ли такое же нарушение."""
        for v in violations:
            if (v.file_path == new_violation.file_path and
                    v.line == new_violation.line and
                    v.column == new_violation.column and
                    v.standard_type == new_violation.standard_type and
                    v.custom_type == new_violation.custom_type):
                return True
        return False

    def _is_type_annotation(self, node: ast.Name) -> bool:
        """Проверить, является ли узел аннотацией типа."""
        parent = getattr(node, 'parent', None)

        if parent is None:
            return False

        # Проверяем различные случаи, где имя используется как тип

        # 1. Аннотация переменной: var: int
        if isinstance(parent, ast.AnnAssign) and parent.annotation == node:
            return True

        # 2. Аннотация аргумента функции: def func(arg: int)
        if isinstance(parent, ast.arg) and parent.annotation == node:
            return True

        # 3. Аннотация возвращаемого значения: def func() -> int:
        if isinstance(parent, ast.FunctionDef) and parent.returns == node:
            return True

        # 4. В составе сложного типа: List[int], Union[int, float]
        # Проверяем, что это не часть индекса сложного типа
        if isinstance(parent, ast.Subscript):
            # Если node это slice (например, int в List[int]), то это индекс
            # Если node это value (например, List в List[int]), то это основной тип
            if hasattr(parent, 'slice') and parent.slice == node:
                # Это индекс, а не основной тип
                return False
            elif isinstance(parent.slice, ast.Index) and hasattr(parent.slice, 'value') and parent.slice.value == node:
                # Это индекс, а не основной тип
                return False
            elif isinstance(parent.slice, ast.Tuple):
                # Если узел в кортеже, проверяем, является ли он элементом кортежа
                if node in parent.slice.elts:
                    return False
            return True

        # 5. В индексе сложного типа: List[int] (для старых версий Python)
        if isinstance(parent, ast.Index) and parent.value == node:
            grandparent = getattr(parent, 'parent', None)
            if isinstance(grandparent, ast.Subscript):
                return False  # Это индекс, а не основной тип

        # 6. В составе кортежа типов: Union[int, float]
        if isinstance(parent, ast.Tuple):
            grandparent = getattr(parent, 'parent', None)
            if isinstance(grandparent, ast.Subscript) and hasattr(grandparent, 'value'):
                if isinstance(grandparent.value, ast.Name) and grandparent.value.id in ('Union', 'Optional'):
                    return True  # Это кортеж типов Union/Optional

        # 7. В type alias: MyType = int
        # Проверяем, что это не присвоение значения, а объявление типа
        if isinstance(parent, ast.Assign):
            # Если это Assign и узел - в списке целей, то это присвоение, а не аннотация
            if node in parent.targets:
                # Это присвоение значения, а не аннотация типа
                return False

        return True

    def _check_annotation(self, node: ast.AST, file_path: Path,
                          lines: List[str], violations: List[TypeViolation]):
        """Проверить аннотацию типа."""
        if isinstance(node, ast.Name):
            self._check_name_node(node, file_path, lines, violations)
        elif isinstance(node, ast.Subscript):
            # Для NDArray[Float] и подобных
            # Проверяем основной тип
            if isinstance(node.value, ast.Name):
                # Не проверяем NDArray типы как нарушения, они уже в списке кастомных
                if node.value.id not in self.config.custom_types.values():
                    self._check_name_node(node.value, file_path, lines, violations)

            # Проверяем внутренний тип
            if isinstance(node.slice, ast.Name):
                self._check_name_node(node.slice, file_path, lines, violations)
            elif isinstance(node.slice, ast.Index) and hasattr(node.slice, 'value'):
                if isinstance(node.slice.value, ast.Name):
                    self._check_name_node(node.slice.value, file_path, lines, violations)
                elif isinstance(node.slice.value, ast.Tuple):
                    for elt in node.slice.value.elts:
                        if isinstance(elt, ast.Name):
                            self._check_name_node(elt, file_path, lines, violations)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Для Union типов (Python 3.10+) int | float
            self._check_annotation(node.left, file_path, lines, violations)
            self._check_annotation(node.right, file_path, lines, violations)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'Union':
            # Для Union[int, float] (старый синтаксис)
            if isinstance(node.slice, ast.Tuple):
                for elt in node.slice.elts:
                    if isinstance(elt, ast.Name):
                        self._check_name_node(elt, file_path, lines, violations)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'Optional':
            # Для Optional[int] (старый синтаксис)
            if isinstance(node.slice, ast.Name):
                self._check_name_node(node.slice, file_path, lines, violations)
            elif isinstance(node.slice, ast.Index) and hasattr(node.slice, 'value'):
                if isinstance(node.slice.value, ast.Name):
                    self._check_name_node(node.slice.value, file_path, lines, violations)

    def _should_ignore(self, node: ast.Name) -> bool:
        """Проверить, нужно ли игнорировать этот узел."""
        # Этот метод больше не используется, оставляем для совместимости
        return False

    def _get_context(self, lines: List[str], line_num: int, context_lines: int = 2) -> str:
        """Получить контекст вокруг строки."""
        start = max(0, line_num - context_lines - 1)
        end = min(len(lines), line_num + context_lines)
        context = []
        for i in range(start, end):
            prefix = ">> " if i == line_num - 1 else "   "
            context.append(f"{prefix}{i + 1}: {lines[i]}")
        return "\n".join(context)

    def scan_directory(self, directory: Union[str, Path]) -> List[TypeViolation]:
        """Сканировать директорию рекурсивно."""
        directory = Path(directory)
        all_violations = []

        for root, dirs, files in os.walk(directory):
            # Исключаем пути из конфига
            dirs[:] = [d for d in dirs if d not in self.config.exclude_paths]

            for file in files:
                if any(file.endswith(ext) for ext in self.config.extensions):
                    file_path = Path(root) / file
                    violations = self.scan_file(file_path)
                    all_violations.extend(violations)

        self.violations = all_violations
        return all_violations

    def get_violations_by_file(self) -> Dict[str, List[TypeViolation]]:
        """Получить нарушения, сгруппированные по файлам."""
        result = {}
        for violation in self.violations:
            if violation.file_path not in result:
                result[violation.file_path] = []
            result[violation.file_path].append(violation)
        return result

    def print_report(self, verbose: bool = False):
        """Вывести отчет о нарушениях."""
        if not self.violations:
            print("✅ Нарушений не найдено! Все типы соответствуют кастомным.")
            return

        by_file = self.get_violations_by_file()
        total = len(self.violations)

        print(
            f"❌ Найдено {total} нарушений (использование стандартных типов вместо кастомных) в {len(by_file)} файлах:\n")

        for file_path, violations in by_file.items():
            print(f"\n📄 {file_path}:")
            for v in violations:
                print(f"  📍 Строка {v.line}, колонка {v.column}")
                print(f"     Используйте кастомный тип '{v.custom_type}' вместо стандартного '{v.standard_type}'")
                print(f"     {v.line_content}")
                if verbose:
                    print(f"\n{v.context}")
                    print("-" * 50)

    def get_fix_suggestions(self) -> Dict[str, List[Tuple[TypeViolation, str]]]:
        """Получить предложения по исправлению."""
        suggestions = {}

        for violation in self.violations:
            if violation.file_path not in suggestions:
                suggestions[violation.file_path] = []

            # Предлагаем замену стандартного типа на кастомный
            new_line = violation.line_content.replace(
                violation.standard_type,
                violation.custom_type
            )
            suggestions[violation.file_path].append((violation, new_line))

        return suggestions