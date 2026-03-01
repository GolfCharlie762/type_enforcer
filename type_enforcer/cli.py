"""CLI интерфейс для Type Enforcer."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .core import TypeEnforcer
from .fixer import TypeFixer
from .config import Config


def create_parser() -> argparse.ArgumentParser:
    """Создать парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Type Enforcer - проверка использования кастомных типов данных",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  type-enforcer scan ./src
  type-enforcer scan ./src --config config.json
  type-enforcer fix ./src --dry-run
  type-enforcer fix ./src --no-backup
  type-enforcer config --init
        """
    )

    parser.add_argument(
        "--version",
        action="version",
        version="Type Enforcer 0.1.0"
    )

    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # Команда scan
    scan_parser = subparsers.add_parser("scan", help="Сканировать файлы")
    scan_parser.add_argument(
        "path",
        help="Путь к файлу или директории для сканирования"
    )
    scan_parser.add_argument(
        "--config", "-c",
        help="Путь к файлу конфигурации"
    )
    scan_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод"
    )
    scan_parser.add_argument(
        "--output", "-o",
        help="Сохранить отчет в файл"
    )

    # Команда fix
    fix_parser = subparsers.add_parser("fix", help="Исправить найденные нарушения")
    fix_parser.add_argument(
        "path",
        help="Путь к файлу или директории для исправления"
    )
    fix_parser.add_argument(
        "--config", "-c",
        help="Путь к файлу конфигурации"
    )
    fix_parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Показать что будет исправлено без фактических изменений"
    )
    fix_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Не создавать резервные копии"
    )
    fix_parser.add_argument(
        "--no-imports",
        action="store_true",
        help="Не добавлять автоматически импорты"
    )

    # Команда config
    config_parser = subparsers.add_parser("config", help="Управление конфигурацией")
    config_parser.add_argument(
        "--init",
        action="store_true",
        help="Создать конфигурацию по умолчанию"
    )
    config_parser.add_argument(
        "--output", "-o",
        default="type_enforcer_config.json",
        help="Путь для сохранения конфигурации"
    )

    return parser


def load_config(config_path: Optional[str]) -> Config:
    """Загрузить конфигурацию."""
    if config_path:
        return Config.from_file(config_path)
    return Config.default()


def handle_scan(args):
    """Обработать команду scan."""
    config = load_config(args.config)
    enforcer = TypeEnforcer(config)

    path = Path(args.path)
    if path.is_file():
        violations = enforcer.scan_file(path)
    else:
        violations = enforcer.scan_directory(path)

    enforcer.print_report(verbose=args.verbose)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            for v in violations:
                f.write(f"{v}\n")
        print(f"\n Отчет сохранен в {args.output}")

    # Возвращаем код ошибки если есть нарушения
    return 1 if violations else 0


def handle_fix(args):
    """Обработать команду fix."""
    config = load_config(args.config)

    # Настраиваем конфиг под fix
    if args.no_backup:
        config.backup_files = False
    if args.no_imports:
        config.auto_add_imports = False

    enforcer = TypeEnforcer(config)

    path = Path(args.path)
    if path.is_file():
        enforcer.scan_file(path)
    else:
        enforcer.scan_directory(path)

    if not enforcer.violations:
        print(" Нарушений не найдено, исправлять нечего!")
        return 0

    fixer = TypeFixer(enforcer)

    if args.dry_run:
        print(" Режим сухого выполнения (без изменений):")
        results = fixer.fix_all(dry_run=True)
        print(f"\n Будет исправлено файлов: {len(results['skipped'])}")
    else:
        print(" Исправление нарушений...")
        results = fixer.fix_all()

        print("\n Результаты:")
        print(f"   Исправлено файлов: {len(results['fixed'])}")
        print(f"   Ошибок при исправлении: {len(results['failed'])}")

        if results["failed"]:
            print("\n  Файлы с ошибками:")
            for f in results["failed"]:
                print(f"    - {f}")

    return 0


def handle_config(args):
    """Обработать команду config."""
    if args.init:
        config = Config.default()
        config.to_file(args.output)
        print(f" Создан файл конфигурации: {args.output}")
        print("\nСодержимое:")
        import json
        print(json.dumps(config.__dict__, indent=2))
        return 0
    else:
        print("Используйте --init для создания конфигурации")
        return 1


def main():
    """Главная функция CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "scan":
            return handle_scan(args)
        elif args.command == "fix":
            return handle_fix(args)
        elif args.command == "config":
            return handle_config(args)
    except KeyboardInterrupt:
        print("\n  Операция прервана пользователем")
        return 130
    except Exception as e:
        print(f"Ошибка: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())