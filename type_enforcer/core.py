"""Основной модуль Type Enforcer."""

import ast
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union, Set
from dataclasses import dataclass
import colorama
from colorama import Fore, Style

# Инициализируем colorama для работы с цветами в терминале
colorama.init(autoreset=True)

from .config import Config


class ParentNodeTransformer(ast.NodeTransformer):
    """Трансформер для добавления ссылок на родительские узлы."""

    def visit(self, node):
        """Посетить узел и добавить ссылку на родителя для детей."""
        for child in ast.iter_child_nodes(node):
            setattr(child, "parent", node)
        self.generic_visit(node)
        return node


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
        return f"{self.file_path}:{self.line}:{self.column + 1} - TC001 Используйте кастомный тип '{self.custom_type}' вместо стандартного '{self.standard_type}'"

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
        self.standard_to_custom: Dict[str, str] = {}
        for custom_type, standard_type in self.config.custom_types.items():
            if standard_type not in self.standard_to_custom:
                self.standard_to_custom[standard_type] = custom_type

        # Компилируем регулярное выражение для поиска type comments
        self.type_comment_pattern = re.compile(r'#\s*type:\s*([^#\n]+)')

        # Множество для отслеживания обработанных узлов
        self._processed_nodes: Set[int] = set()

        # Типы-контейнеры, которые не нужно проверять как стандартные
        self.container_types: Set[str] = {"List", "Dict", "Set", "Tuple", "Optional", "Union", "Any"}

    def scan_file(self, file_path: Union[str, Path]) -> List[TypeViolation]:
        """Сканировать один файл на нарушения."""
        file_path = Path(file_path)
        violations: List[TypeViolation] = []
        self._processed_nodes.clear()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            # Добавляем ссылки на родительские узлы
            transformer = ParentNodeTransformer()
            tree = transformer.visit(tree)

            lines = content.splitlines()

            # Найти все узлы, где используются имена типов
            for node in ast.walk(tree):
                node_id = id(node)
                if node_id in self._processed_nodes:
                    continue

                self._processed_nodes.add(node_id)

                if isinstance(node, ast.Name):
                    self._check_name_node(node, file_path, lines, violations)
                elif isinstance(node, ast.AnnAssign) and node.annotation:
                    self._check_annotation(
                        node.annotation, file_path, lines, violations
                    )
                elif isinstance(node, ast.FunctionDef):
                    self._check_function_node(node, file_path, lines, violations)
                elif isinstance(node, ast.Assign):
                    self._check_assign_node(node, file_path, lines, violations)
                elif isinstance(node, ast.arg) and node.annotation:
                    self._check_annotation(
                        node.annotation, file_path, lines, violations
                    )

        except SyntaxError as e:
            print(f"Синтаксическая ошибка в файле {file_path}: {e}")
        except Exception as e:
            print(f"Ошибка при сканировании {file_path}: {e}")

        self.violations = violations
        return violations

    def _check_function_node(
            self,
            node: ast.FunctionDef,
            file_path: Path,
            lines: List[str],
            violations: List[TypeViolation]
    ):
        """Проверить узел функции на нарушения."""
        # Проверяем возвращаемый тип
        if node.returns:
            self._check_annotation(node.returns, file_path, lines, violations)

        # Проверяем аргументы
        args = node.args
        all_args = []

        # Обычные аргументы
        all_args.extend(args.args)
        # Аргументы только по ключу
        all_args.extend(args.kwonlyargs)
        # Аргументы с переменным количеством
        if args.vararg:
            all_args.append(args.vararg)
        if args.kwarg:
            all_args.append(args.kwarg)

        for arg in all_args:
            if arg.annotation:
                self._check_annotation(arg.annotation, file_path, lines, violations)

    def _check_assign_node(
            self,
            node: ast.Assign,
            file_path: Path,
            lines: List[str],
            violations: List[TypeViolation]
    ):
        """Проверить узел присваивания на нарушения."""
        # Проверяем type comments
        if hasattr(node, "type_comment") and node.type_comment:
            self._check_type_comment(node, file_path, lines, violations)

        # Проверяем строку на наличие type comment
        if hasattr(node, "lineno") and node.lineno > 0:
            line_idx = node.lineno - 1
            if line_idx < len(lines):
                self._check_line_for_type_comment(
                    lines[line_idx],
                    node.lineno,
                    file_path,
                    lines,
                    violations
                )

    def _check_type_comment(
            self,
            node: ast.AST,
            file_path: Path,
            lines: List[str],
            violations: List[TypeViolation],
    ):
        """Проверить type comment на наличие стандартных типов."""
        if not hasattr(node, "type_comment") or not node.type_comment:
            return

        type_comment = node.type_comment
        line_num = getattr(node, "lineno", 0)

        # Парсим type comment
        try:
            # Пробуем распарсить type comment как аннотацию типа
            parsed_type = ast.parse(type_comment, mode="eval").body

            # Рекурсивно проверяем все имена в распарсенном типе
            self._check_type_comment_node(parsed_type, file_path, line_num, lines, violations, type_comment)
        except SyntaxError:
            # Если не удалось распарсить, ищем стандартные типы через регулярные выражения
            self._check_type_comment_regex(type_comment, file_path, line_num, lines, violations)

    def _check_type_comment_node(
            self,
            node: ast.AST,
            file_path: Path,
            line_num: int,
            lines: List[str],
            violations: List[TypeViolation],
            original_comment: str
    ):
        """Рекурсивно проверить узлы распарсенного type comment."""
        if isinstance(node, ast.Name):
            if node.id in self.standard_to_custom:
                line_content = lines[line_num - 1].strip() if line_num <= len(lines) else ""

                # Находим колонку, где начинается стандартный тип в комментарии
                comment_part = line_content.split('#', 1)[1] if '#' in line_content else ""
                col_in_comment = original_comment.find(node.id)
                col_offset = line_content.find(comment_part) + col_in_comment if comment_part else 0

                violation = TypeViolation(
                    file_path=str(file_path),
                    line=line_num,
                    column=max(0, col_offset),
                    custom_type=self.standard_to_custom[node.id],
                    standard_type=node.id,
                    line_content=line_content,
                    context=self._get_context(lines, line_num),
                )

                if not self._violation_exists(violations, violation):
                    violations.append(violation)

        # Рекурсивно проверяем дочерние узлы
        for child in ast.iter_child_nodes(node):
            self._check_type_comment_node(child, file_path, line_num, lines, violations, original_comment)

    def _check_type_comment_regex(
            self,
            type_comment: str,
            file_path: Path,
            line_num: int,
            lines: List[str],
            violations: List[TypeViolation]
    ):
        """Проверить type comment с помощью регулярных выражений."""
        if line_num > len(lines):
            return

        line_content = lines[line_num - 1].strip()

        # Ищем все стандартные типы в комментарии
        for std_type, custom_type in self.standard_to_custom.items():
            pattern = r'\b' + re.escape(std_type) + r'\b'
            for match in re.finditer(pattern, type_comment):
                comment_part = line_content.split('#', 1)[1] if '#' in line_content else ""
                col_in_comment = match.start()
                col_offset = line_content.find(comment_part) + col_in_comment if comment_part else 0

                violation = TypeViolation(
                    file_path=str(file_path),
                    line=line_num,
                    column=max(0, col_offset),
                    custom_type=custom_type,
                    standard_type=std_type,
                    line_content=line_content,
                    context=self._get_context(lines, line_num),
                )

                if not self._violation_exists(violations, violation):
                    violations.append(violation)

    def _check_line_for_type_comment(
            self,
            line: str,
            line_num: int,
            file_path: Path,
            lines: List[str],
            violations: List[TypeViolation]
    ):
        """Проверить строку на наличие type comment."""
        match = self.type_comment_pattern.search(line)
        if match:
            type_comment = match.group(1).strip()
            self._check_type_comment_regex(type_comment, file_path, line_num, lines, violations)

    def _check_name_node(
            self,
            node: ast.Name,
            file_path: Path,
            lines: List[str],
            violations: List[TypeViolation],
    ):
        """Проверить узел с именем."""
        if node.id in self.standard_to_custom and self._is_type_annotation(node):
            line_content = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""

            violation = TypeViolation(
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                custom_type=self.standard_to_custom[node.id],
                standard_type=node.id,
                line_content=line_content,
                context=self._get_context(lines, node.lineno),
            )

            if not self._violation_exists(violations, violation):
                violations.append(violation)

    def _violation_exists(
            self, violations: List[TypeViolation], new_violation: TypeViolation
    ) -> bool:
        """Проверить, существует ли такое же нарушение."""
        for v in violations:
            if (v.file_path == new_violation.file_path and
                    v.line == new_violation.line and
                    v.column == new_violation.column and
                    v.standard_type == new_violation.standard_type):
                return True
        return False

    def _is_type_annotation(self, node: ast.Name) -> bool:
        """Проверить, является ли узел аннотацией типа."""
        parent = getattr(node, "parent", None)

        if parent is None:
            return False

        # Пропускаем имена, которые являются названиями контейнеров
        if node.id in self.container_types:
            return False

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
        if isinstance(parent, ast.Subscript):
            # Проверяем, является ли узел частью среза (внутренним типом)
            if hasattr(parent, "slice"):
                # Если это сам срез
                if parent.slice == node:
                    return True
                # Если это значение в индексе
                if isinstance(parent.slice, ast.Index):
                    if getattr(parent.slice, "value", None) == node:
                        return True
                # Если это элемент кортежа в срезе
                if isinstance(parent.slice, ast.Tuple):
                    if node in parent.slice.elts:
                        return True
            return True

        # 5. В составе кортежа типов: Union[int, float]
        if isinstance(parent, ast.Tuple):
            grandparent = getattr(parent, "parent", None)
            if isinstance(grandparent, ast.Subscript):
                if isinstance(grandparent.value, ast.Name):
                    if grandparent.value.id in ("Union", "Optional"):
                        return True
            return True

        # 6. В type alias: MyType = int
        if isinstance(parent, ast.Assign):
            if node not in parent.targets:
                return True

        # 7. В возвращаемом типе свойства (@property)
        if isinstance(parent, ast.FunctionDef) and parent.returns == node:
            return True

        # 8. В индексе (для старых версий Python)
        if isinstance(parent, ast.Index):
            grandparent = getattr(parent, "parent", None)
            if isinstance(grandparent, ast.Subscript):
                return True

        return False

    def _check_annotation(
            self,
            node: ast.AST,
            file_path: Path,
            lines: List[str],
            violations: List[TypeViolation],
            parent_context: Optional[str] = None
    ):
        """Проверить аннотацию типа рекурсивно."""
        node_id = id(node)
        if node_id in self._processed_nodes:
            return
        self._processed_nodes.add(node_id)

        if isinstance(node, ast.Name):
            self._check_name_node(node, file_path, lines, violations)

        elif isinstance(node, ast.Subscript):
            # Проверяем основной тип контейнера (List, Dict и т.д.)
            if isinstance(node.value, ast.Name):
                if node.value.id not in self.container_types:
                    self._check_name_node(node.value, file_path, lines, violations)

            # Проверяем срез (внутренние типы)
            self._check_annotation(node.slice, file_path, lines, violations, "subscript_slice")

        elif isinstance(node, ast.Index):
            # Для старых версий Python
            if hasattr(node, "value"):
                self._check_annotation(node.value, file_path, lines, violations, "index")

        elif isinstance(node, ast.Tuple):
            # Для кортежей типов (например, в Dict[str, float] или Union[int, float])
            for elt in node.elts:
                self._check_annotation(elt, file_path, lines, violations, "tuple_element")

        elif isinstance(node, ast.List):
            # Для списков типов
            for elt in node.elts:
                self._check_annotation(elt, file_path, lines, violations, "list_element")

        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Для Union типов (Python 3.10+)
            self._check_annotation(node.left, file_path, lines, violations, "binop_left")
            self._check_annotation(node.right, file_path, lines, violations, "binop_right")

        elif isinstance(node, ast.Attribute):
            # Для типов с точкой: np.float64
            if node.attr in self.standard_to_custom:
                # Создаем виртуальный Name узел для проверки
                virtual_node = ast.Name(
                    id=node.attr,
                    lineno=node.lineno,
                    col_offset=node.col_offset + len(getattr(node.value, "id", "")) + 1
                )
                self._check_name_node(virtual_node, file_path, lines, violations)

        elif isinstance(node, ast.Constant):
            # Для констант (например, None)
            pass

        elif isinstance(node, ast.Call):
            # Для вызовов (например, Union[int, float])
            if isinstance(node.func, ast.Name):
                if node.func.id in self.container_types:
                    for arg in node.args:
                        self._check_annotation(arg, file_path, lines, violations, "call_arg")
                else:
                    self._check_name_node(node.func, file_path, lines, violations)

    def _get_context(
            self, lines: List[str], line_num: int, context_lines: int = 2
    ) -> str:
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
        result: Dict[str, List[TypeViolation]] = {}
        for violation in self.violations:
            if violation.file_path not in result:
                result[violation.file_path] = []
            result[violation.file_path].append(violation)
        return result

    def print_report(self, verbose: bool = False):
        """Вывести отчет о нарушениях."""
        if not self.violations:
            print(f"{Fore.GREEN} Нарушений не найдено! Все типы соответствуют кастомным.{Style.RESET_ALL}")
            return

        by_file = self.get_violations_by_file()
        total = len(self.violations)

        print(
            f"{Fore.CYAN} Найдено {total} нарушений в {len(by_file)} файлах:{Style.RESET_ALL}\n"
        )

        for file_path, violations in by_file.items():
            print(f"\n{Fore.YELLOW}{file_path}:{Style.RESET_ALL}")

            # Сортируем нарушения по строке и колонке
            violations.sort(key=lambda v: (v.line, v.column))

            for i, v in enumerate(violations, 1):
                abs_path = os.path.abspath(v.file_path)
                clickable_link = f"file://{abs_path}:{v.line}:{v.column + 1}"

                print(f"  {Fore.BLUE}[{i}] {clickable_link}{Style.RESET_ALL}")
                print(f"      {Fore.RED}Строка {v.line}, колонка {v.column + 1}{Style.RESET_ALL}")
                print(
                    f"      {Fore.RED}Используйте кастомный тип {Fore.GREEN}'{v.custom_type}'{Fore.RED} вместо стандартного {Fore.YELLOW}'{v.standard_type}'{Style.RESET_ALL}"
                )

                # Подсвечиваем проблемный участок
                highlighted_line = self._highlight_error_in_line(
                    v.line_content, v.standard_type
                )
                print(f"      {highlighted_line}")

                # Добавляем указатель на проблемное место
                pointer = " " * (v.column + 6) + "^"
                print(f"{Fore.RED}{pointer}{Style.RESET_ALL}")

                if verbose:
                    print(f"\n{v.context}")
                    print("-" * 50)

                if i < len(violations):
                    print()

    def _highlight_error_in_line(self, line_content: str, error_type: str) -> str:
        """Подсветить все вхождения ошибочного типа в строке кода."""
        result = line_content
        # Используем регулярное выражение для поиска целых слов
        pattern = re.compile(r'\b' + re.escape(error_type) + r'\b')

        # Находим все совпадения и подсвечиваем их
        matches = list(pattern.finditer(line_content))
        for match in reversed(matches):  # Идём с конца, чтобы не сбивать позиции
            start, end = match.span()
            before = result[:start]
            error = result[start:end]
            after = result[end:]
            result = f"{before}{Fore.RED}{error}{Style.RESET_ALL}{after}"

        return result

    def get_fix_suggestions(self) -> Dict[str, List[Tuple[TypeViolation, str]]]:
        """Получить предложения по исправлению."""
        suggestions: Dict[str, List[Tuple[TypeViolation, str]]] = {}

        for violation in self.violations:
            if violation.file_path not in suggestions:
                suggestions[violation.file_path] = []

            # Предлагаем замену стандартного типа на кастомный
            new_line = violation.line_content
            # Заменяем только конкретное вхождение типа
            pattern = re.compile(r'\b' + re.escape(violation.standard_type) + r'\b')

            # Находим все вхождения и заменяем только то, которое соответствует позиции
            for match in pattern.finditer(new_line):
                if match.start() == violation.column:
                    new_line = (new_line[:match.start()] +
                                violation.custom_type +
                                new_line[match.end():])
                    break

            suggestions[violation.file_path].append((violation, new_line))

        return suggestions