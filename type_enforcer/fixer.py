"""Модуль для автоматического исправления нарушений."""

from pathlib import Path
from typing import List, Dict, Tuple, Set
import re

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

            # Проверяем наличие директивы #ignore-type в начале файла
            if self._has_ignore_directive(lines):
                print(f"⏭️ Пропущен файл {file_path} (директива #ignore-type)")
                return True

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
                
                # Проверяем наличие директивы #ignore-type в строке
                if self._line_has_ignore_directive(original_line):
                    continue
                
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
                    
                    # Для составных типов (например np.float64) нужно заменить полностью
                    # Проверяем, является ли old_type составным (содержит точку)
                    if '.' in old_type:
                        # Заменяем полное вхождение составного типа
                        parts_after = parts_after.replace(old_type, new_type, 1)
                    else:
                        # Для простых типов (int, float, bool) заменяем только если это не вызов функции
                        # Ищем границу слова после типа
                        # Создаем паттерн, который матчит слово целиком
                        pattern = r'\b' + re.escape(old_type) + r'\b'
                        match = re.search(pattern, parts_after)
                        if match:
                            # Заменяем только первое совпадение
                            parts_after = parts_after[:match.start()] + new_type + parts_after[match.end():]
                    
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

    def _has_ignore_directive(self, lines: List[str]) -> bool:
        """Проверить наличие директивы #ignore-type в начале файла."""
        for i, line in enumerate(lines[:5]):  # Проверяем первые 5 строк
            if '#ignore-type' in line or '# ignore-type' in line:
                return True
        return False
    
    def _line_has_ignore_directive(self, line: str) -> bool:
        """Проверить наличие директивы #ignore-type в строке."""
        return '#ignore-type' in line or '# ignore-type' in line

    def _add_missing_imports(
        self, lines: List[str], fixes: List[Tuple[TypeViolation, str]]
    ) -> List[str]:
        """Добавить недостающие импорты для кастомных типов."""
        # Собираем используемые кастомные типы
        used_types: Set[str] = set()
        for violation, _ in fixes:
            used_types.add(violation.custom_type)

        # Находим существующие импорты и анализируем их
        import_lines = []
        existing_imports: Dict[str, Set[str]] = {}  # module -> set of imported names
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                import_lines.append(i)
                
                # Парсим импорт для понимания что уже импортировано
                if stripped.startswith("from "):
                    # from X import A, B, C
                    parts = stripped.split(" import ")
                    if len(parts) == 2:
                        module_part = parts[0].replace("from ", "").strip()
                        imports_part = parts[1].strip()
                        
                        # Разбираем импортированные имена (может быть несколько через запятую)
                        imported_names = [name.strip().split(" as ")[-1].strip() 
                                         for name in imports_part.split(",")]
                        
                        if module_part not in existing_imports:
                            existing_imports[module_part] = set()
                        existing_imports[module_part].update(imported_names)

        # Формируем список новых импортов
        new_imports: List[str] = []
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
                # Для многострочных импортов (как NDArrayFloat)
                for imp_line in import_stmt.split("\n"):
                    imp_stripped = imp_line.strip()
                    if not imp_stripped:
                        continue
                    
                    # Пропускаем строки, которые являются просто именами типов без "import" или "from"
                    if not ("import" in imp_stripped or "from" in imp_stripped):
                        continue
                    
                    # Проверяем, нет ли уже такого импорта
                    # Анализируем структуру импорта
                    already_exists = False
                    
                    if imp_stripped.startswith("from "):
                        # from X import Y
                        parts = imp_stripped.split(" import ")
                        if len(parts) == 2:
                            module_part = parts[0].replace("from ", "").strip()
                            type_to_import = parts[1].strip().split(" as ")[0].strip()
                            
                            # Проверяем, импортирован ли уже этот тип из этого модуля
                            if module_part in existing_imports:
                                if type_to_import in existing_imports[module_part]:
                                    already_exists = True
                                    break
                    else:
                        # import X
                        # Простая проверка на точное совпадение
                        for line in lines:
                            line_stripped = line.strip()
                            if line_stripped == imp_stripped:
                                already_exists = True
                                break
                    
                    if not already_exists and imp_stripped not in new_imports:
                        new_imports.append(imp_stripped)

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
                in_docstring = False
                docstring_end = 0
                
                # Ищем конец docstring (если есть)
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    
                    # Проверяем начало/конец многострочного docstring
                    if not in_docstring:
                        if stripped.startswith('"""') or stripped.startswith("'''"):
                            # Однострочный docstring
                            if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                                docstring_end = i + 1
                            else:
                                in_docstring = True
                    else:
                        # Ищем конец многострочного docstring
                        if '"""' in stripped or "'''" in stripped:
                            in_docstring = False
                            docstring_end = i + 1
                
                # Пропускаем docstring и комментарии в начале
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if i >= docstring_end:
                        if stripped and not stripped.startswith("#"):
                            insert_pos = i
                            break
                        elif stripped:
                            # Это комментарий после docstring, вставляем после него
                            insert_pos = i + 1

                for imp in reversed(new_imports):
                    lines.insert(insert_pos, imp + "\n")

        return lines
