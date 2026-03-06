"""Модуль для автоматического исправления нарушений."""

from pathlib import Path
from typing import List, Dict, Tuple, Set

from .core import TypeEnforcer, TypeViolation
from .config import DEFAULT_IMPORTS


class TypeFixer:
    """Класс для исправления нарушений использования типов."""

    def __init__(self, enforcer: TypeEnforcer):
        self.enforcer = enforcer
        self.fixed_files: List[str] = []
        self.failed_files: List[str] = []

    def fix_all(self, dry_run: bool = False) -> Dict[str, List[str]]:
        """Исправить все найденные нарушения."""
        results: Dict[str, List[str]] = {"fixed": [], "failed": [], "skipped": []}

        # Используем уже найденные нарушения
        if not self.enforcer.violations:
            # Если нарушения еще не найдены, сканируем файл
            # Но для этого нужно знать, какой файл проверять
            pass

        suggestions = self.enforcer.get_fix_suggestions()

        for file_path, fixes in suggestions.items():
            if dry_run:
                print(f"🔍 Сухое выполнение для {file_path}:")
                for violation, new_line in fixes:
                    print(f"  Строка {violation.line}: {violation.line_content}")
                    print(f"      -> {new_line}")
                results["skipped"].append(file_path)
                continue

            success = self._fix_file(file_path, fixes)
            if success:
                results["fixed"].append(file_path)
                self.fixed_files.append(file_path)
            else:
                results["failed"].append(file_path)
                self.failed_files.append(file_path)

        return results

    def _fix_file(self, file_path: str, fixes: List[Tuple[TypeViolation, str]]) -> bool:
        """Исправить один файл."""
        try:
            path = Path(file_path)

            # Читаем файл
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Применяем исправления (в обратном порядке, чтобы не сбивать номера строк)
            # Группируем исправления по строкам
            fixes_by_line: Dict[int, List[Tuple[TypeViolation, str]]] = {}
            for violation, new_line in fixes:
                line_idx = violation.line - 1
                if line_idx not in fixes_by_line:
                    fixes_by_line[line_idx] = []
                fixes_by_line[line_idx].append((violation, new_line))
            
            # Применяем исправления для каждой строки
            for line_idx, line_fixes in fixes_by_line.items():
                original_line = lines[line_idx]
                
                # Сортируем исправления в строке по позиции в обратном порядке
                line_fixes.sort(key=lambda x: x[0].column, reverse=True)
                
                # Применяем каждое исправление в строке
                modified_line = original_line
                for violation, new_content in line_fixes:
                    # Определяем стандартный и кастомный типы для замены
                    old_type = violation.standard_type
                    new_type = violation.custom_type
                    
                    # Заменяем только конкретное вхождение типа, учитывая позицию
                    # Находим позицию в строке и делаем точечную замену
                    parts_before = modified_line[:violation.column]
                    parts_after = modified_line[violation.column:]
                    
                    # Заменяем первое вхождение старого типа в части после позиции
                    parts_after = parts_after.replace(old_type, new_type, 1)
                    
                    modified_line = parts_before + parts_after
                
                # Сохраняем отступы исходной строки
                leading_whitespace = ""
                for char in original_line:
                    if char in (' ', '\t'):
                        leading_whitespace += char
                    else:
                        break
                
                # Применяем исправление с сохранением отступов
                lines[line_idx] = leading_whitespace + modified_line.lstrip()

            # Добавляем необходимые импорты
            if self.enforcer.config.auto_add_imports:
                lines = self._add_missing_imports(lines, fixes)

            # Записываем изменения
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            print(f" Исправлен файл: {file_path}")
            return True

        except Exception as e:
            print(f" Ошибка при исправлении {file_path}: {e}")
            return False

    def _add_missing_imports(
        self, lines: List[str], fixes: List[Tuple[TypeViolation, str]]
    ) -> List[str]:
        """Добавить недостающие импорты для кастомных типов."""
        # Собираем используемые кастомные типы
        used_types: Set[str] = set()
        for violation, _ in fixes:
            used_types.add(violation.custom_type)

        # Находим существующие импорты
        import_lines = []
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                import_lines.append(i)

        # Формируем список новых импортов
        new_imports = []
        file_path = self.enforcer.violations[0].file_path if self.enforcer.violations else None
        
        for type_name in used_types:
            # Получаем импорт из конфига (с учетом относительных путей)
            import_stmt = None
            if file_path and hasattr(self.enforcer.config, 'get_import_for_type'):
                import_stmt = self.enforcer.config.get_import_for_type(type_name, file_path)
            
            # Если не нашли в конфиге, пробуем стандартные импорты
            if import_stmt is None:
                import_stmt = DEFAULT_IMPORTS.get(type_name)
            
            if import_stmt:
                # Проверяем, нет ли уже такого импорта
                if not any(import_stmt.strip() in line for line in lines):
                    # Для многострочных импортов (как NDArrayFloat)
                    for imp_line in import_stmt.split("\n"):
                        if imp_line.strip() and not any(
                            imp_line.strip() in line for line in lines
                        ):
                            new_imports.append(imp_line)

        # Добавляем новые импорты
        if new_imports:
            if import_lines:
                # Вставляем после последнего импорта
                insert_pos = import_lines[-1] + 1
                for imp in reversed(new_imports):
                    lines.insert(insert_pos, imp + "\n")
            else:
                # Добавляем в начало файла (после возможных докстрингов)
                insert_pos = 0
                # Пропускаем докстринги и комментарии в начале
                for i, line in enumerate(lines):
                    if (
                        line.strip()
                        and not line.startswith('"""')
                        and not line.startswith("'''")
                        and not line.startswith("#")
                    ):
                        insert_pos = i
                        break

                for imp in reversed(new_imports):
                    lines.insert(insert_pos, imp + "\n")

        return lines
