"""Модуль для автоматического исправления нарушений."""

import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Set
from datetime import datetime

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
        results = {"fixed": [], "failed": [], "skipped": []}

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

            # Создаем резервную копию
            if self.enforcer.config.backup_files:
                backup_path = path.with_suffix(
                    f"{path.suffix}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                shutil.copy2(path, backup_path)
                print(f"📦 Создана резервная копия: {backup_path}")

            # Читаем файл
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Применяем исправления (в обратном порядке, чтобы не сбивать номера строк)
            fixes.sort(key=lambda x: x[0].line, reverse=True)

            for violation, new_line in fixes:
                line_idx = violation.line - 1
                # Убираем лишние пробелы в конце, но сохраняем форматирование
                lines[line_idx] = new_line.rstrip() + "\n"

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
        for type_name in used_types:
            if type_name in DEFAULT_IMPORTS:
                import_stmt = DEFAULT_IMPORTS[type_name]
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
