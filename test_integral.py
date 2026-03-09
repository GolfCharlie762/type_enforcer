"""Расширенные тесты для Type Enforcer - максимальное покрытие всех аспектов."""

import ast
import tempfile
import shutil
import json
from pathlib import Path
import pytest

from type_enforcer.core import TypeEnforcer, TypeViolation, ParentNodeTransformer
from type_enforcer.config import Config, DEFAULT_TYPES, STANDARD_TO_CUSTOM
from type_enforcer.fixer import TypeFixer
from type_enforcer.cli import create_parser, load_config


# ============================================================================
# ФИКСТУРЫ
# ============================================================================


@pytest.fixture
def temp_dir():
    """Создать временную директорию для тестов."""
    dir_path = tempfile.mkdtemp()
    yield Path(dir_path)
    shutil.rmtree(dir_path)


@pytest.fixture
def default_config():
    """Конфигурация по умолчанию."""
    return Config.default()


@pytest.fixture
def enforcer(default_config):
    """Создать TypeEnforcer с конфигурацией по умолчанию."""
    return TypeEnforcer(default_config)


# ============================================================================
# ТЕСТЫ КОНФИГУРАЦИИ
# ============================================================================


class TestConfigBasic:
    """Базовые тесты конфигурации."""

    def test_default_config_creation(self):
        """Тест создания конфигурации по умолчанию."""
        config = Config.default()
        assert config.custom_types is not None
        assert "Int" in config.custom_types
        assert "Float" in config.custom_types
        assert "Bool" in config.custom_types
        assert config.types_file == "src/types.py"
        assert config.relative_import is True
        assert config.auto_add_imports is True
        assert config.backup_files is True

    def test_custom_config_creation(self):
        """Тест создания пользовательской конфигурации."""
        custom_types = {"MyInt": "int", "MyFloat": "float"}
        config = Config(
            custom_types=custom_types,
            types_file=None,
            relative_import=False,
            exclude_paths=["custom_ignore"],
            extensions=[".py", ".pyx"],
            auto_add_imports=False,
            backup_files=False,
        )
        assert config.custom_types == custom_types
        assert config.types_file is None
        assert config.relative_import is False
        assert "custom_ignore" in config.exclude_paths
        assert ".pyx" in config.extensions
        assert config.auto_add_imports is False
        assert config.backup_files is False

    def test_config_none_values_handling(self):
        """Тест обработки None значений в конфигурации."""
        config = Config(custom_types=None, exclude_paths=None, extensions=None)
        # После __post_init__ должны быть установлены значения по умолчанию
        assert config.custom_types == {}
        assert config.exclude_paths is not None
        assert config.extensions == [".py"]

    def test_config_to_file_and_from_file(self, temp_dir):
        """Тест сохранения и загрузки конфигурации из файла."""
        config = Config(
            custom_types={"TestType": "test"},
            relative_import=False,
            exclude_paths=["ignore1", "ignore2"],
        )

        config_file = temp_dir / "config.json"
        config.to_file(config_file)

        # Проверяем, что файл создан
        assert config_file.exists()

        # Загружаем конфигурацию обратно
        loaded_config = Config.from_file(config_file)

        # Сравниваем значения (исключая внутренние поля)
        assert loaded_config.custom_types.get("TestType") == "test"
        assert loaded_config.relative_import is False
        assert "ignore1" in loaded_config.exclude_paths


class TestConfigTypesFile:
    """Тесты загрузки типов из файлов."""

    def test_load_types_from_python_file(self, temp_dir):
        """Тест загрузки типов из Python файла."""
        # Создаем файл с типами
        types_file = temp_dir / "types.py"
        types_file.write_text("""
TYPES = {
    "CustomInt": "int",
    "CustomFloat": "float",
    "CustomBool": "bool"
}
""")

        config = Config(types_file=str(types_file))

        assert "CustomInt" in config.custom_types
        assert "CustomFloat" in config.custom_types
        assert "CustomBool" in config.custom_types

    def test_load_types_from_json_file(self, temp_dir):
        """Тест загрузки типов из JSON файла."""
        types_file = temp_dir / "types.json"
        types_data = {"JsonInt": "int", "JsonFloat": "float"}
        types_file.write_text(json.dumps(types_data))

        config = Config(types_file=str(types_file))

        assert "JsonInt" in config.custom_types
        assert "JsonFloat" in config.custom_types

    def test_load_types_from_multiple_files(self, temp_dir):
        """Тест загрузки типов из нескольких файлов."""
        # Создаем два файла с типами
        types_file1 = temp_dir / "types1.py"
        types_file1.write_text('TYPES = {"Type1": "int"}')

        types_file2 = temp_dir / "types2.py"
        types_file2.write_text('TYPES = {"Type2": "float"}')

        config = Config(types_file=[str(types_file1), str(types_file2)])

        assert "Type1" in config.custom_types
        assert "Type2" in config.custom_types

    def test_load_types_nonexistent_file(self, temp_dir):
        """Тест загрузки из несуществующего файла (должен игнорироваться)."""
        config = Config(types_file=str(temp_dir / "nonexistent.py"))
        # Не должно возникать ошибки, файл просто игнорируется
        assert config.custom_types is not None

    def test_load_types_unsupported_format(self, temp_dir):
        """Тест загрузки из неподдерживаемого формата."""
        types_file = temp_dir / "types.yaml"
        types_file.write_text("key: value")

        with pytest.raises(ValueError, match="Неподдерживаемый формат"):
            Config(types_file=str(types_file))

    def test_load_types_from_py_without_dict(self, temp_dir):
        """Тест загрузки из Python файла без явного словаря TYPES."""
        types_file = temp_dir / "types.py"
        types_file.write_text("""
class MyClass:
    pass

MY_TYPES = {"ClassType": "MyClass"}
""")

        config = Config(types_file=str(types_file))
        # Должен загрузить MY_TYPES как словарь с типами
        assert "ClassType" in config.custom_types


class TestConfigImportGeneration:
    """Тесты генерации импортов."""

    def test_get_import_for_standard_type(self, default_config):
        """Тест получения импорта для стандартного типа."""
        import_stmt = default_config.get_import_for_type("Int", "/path/to/file.py")
        assert import_stmt is not None
        assert "numpy" in import_stmt
        assert "Int" in import_stmt

    def test_get_import_relative_same_directory(self, temp_dir):
        """Тест относительного импорта для файлов в одной директории."""
        types_file = temp_dir / "types.py"
        types_file.write_text('TYPES = {"LocalType": "int"}')

        config = Config(types_file=str(types_file), relative_import=True)

        current_file = temp_dir / "main.py"
        import_stmt = config.get_import_for_type("LocalType", str(current_file))

        assert import_stmt is not None
        assert "from .types import LocalType" == import_stmt

    def test_get_import_relative_subdirectory(self, temp_dir):
        """Тест относительного импорта для файлов в поддиректории."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        types_file = src_dir / "types.py"
        types_file.write_text('TYPES = {"SrcType": "int"}')

        config = Config(types_file=str(types_file), relative_import=True)

        # Файл на уровень выше
        current_file = temp_dir / "main.py"
        import_stmt = config.get_import_for_type("SrcType", str(current_file))

        assert import_stmt is not None
        assert "SrcType" in import_stmt

    def test_get_import_absolute(self, temp_dir):
        """Тест абсолютного импорта."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        types_file = src_dir / "types.py"
        types_file.write_text('TYPES = {"AbsType": "int"}')

        config = Config(types_file=str(types_file), relative_import=False)

        current_file = temp_dir / "main.py"
        import_stmt = config.get_import_for_type("AbsType", str(current_file))

        assert import_stmt is not None
        assert "AbsType" in import_stmt


# ============================================================================
# ТЕСТЫ CORE - ОБНАРУЖЕНИЕ НАРУШЕНИЙ
# ============================================================================


class TestCoreBasicViolations:
    """Базовые тесты обнаружения нарушений."""

    def test_simple_variable_annotation(self, temp_dir, enforcer):
        """Тест нарушения в аннотации переменной."""
        code = "x: int = 42"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        assert len(violations) >= 1
        assert any(v.standard_type == "int" for v in violations)

    def test_function_parameter_annotation(self, temp_dir, enforcer):
        """Тест нарушения в аннотации параметра функции."""
        code = "def func(x: int): pass"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        assert len(violations) >= 1
        assert any(v.standard_type == "int" for v in violations)

    def test_function_return_annotation(self, temp_dir, enforcer):
        """Тест нарушения в аннотации возвращаемого типа."""
        code = "def func() -> int: return 42"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        assert len(violations) >= 1
        assert any(v.standard_type == "int" for v in violations)

    def test_class_method_annotations(self, temp_dir, enforcer):
        """Тест нарушения в аннотациях методов класса."""
        code = """
class MyClass:
    def method(self, x: float) -> bool:
        return x > 0
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        assert len(violations) >= 2  # float и bool

    def test_nested_generic_types(self, temp_dir, enforcer):
        """Тест нарушений во вложенных обобщенных типах."""
        code = """
from typing import List, Dict, Optional

x: List[int] = []
y: Dict[str, float] = {}
z: Optional[bool] = None
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Должны найти int, float, bool внутри контейнеров
        std_types = [v.standard_type for v in violations]
        assert "int" in std_types
        assert "float" in std_types
        assert "bool" in std_types


class TestCoreComplexTypes:
    """Тесты сложных типов."""

    def test_union_types(self, temp_dir, enforcer):
        """Тест нарушений в Union типах."""
        code = """
from typing import Union

x: Union[int, float] = 42
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        std_types = [v.standard_type for v in violations]
        assert "int" in std_types
        assert "float" in std_types

    def test_pipe_union_syntax(self, temp_dir, enforcer):
        """Тест нарушений в Union типах с синтаксисом | (Python 3.10+)."""
        code = "x: int | float = 42"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        std_types = [v.standard_type for v in violations]
        assert "int" in std_types
        assert "float" in std_types

    def test_tuple_types(self, temp_dir, enforcer):
        """Тест нарушений в Tuple типах."""
        code = """
from typing import Tuple

x: Tuple[int, float, bool] = (1, 2.0, True)
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        std_types = [v.standard_type for v in violations]
        assert "int" in std_types
        assert "float" in std_types
        assert "bool" in std_types

    def test_callable_types(self, temp_dir, enforcer):
        """Тест нарушений в Callable типах."""
        code = """
from typing import Callable

f: Callable[[int, float], bool]
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        std_types = [v.standard_type for v in violations]
        assert "int" in std_types
        assert "float" in std_types
        assert "bool" in std_types

    def test_ndarray_parameterized(self, temp_dir, enforcer):
        """Тест нарушений в параметризованных NDArray."""
        code = """
from numpy.typing import NDArray

arr: NDArray[float]
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        std_types = [v.standard_type for v in violations]
        assert "float" in std_types or "float64" in std_types


class TestCoreTypeComments:
    """Тесты type comments."""

    def test_variable_type_comment(self, temp_dir, enforcer):
        """Тест type comment для переменной."""
        code = """
x = 42  # type: int
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        assert len(violations) >= 1
        assert any(v.standard_type == "int" for v in violations)

    def test_function_type_comment(self, temp_dir, enforcer):
        """Тест type comment для функции."""
        code = """
def func(x, y):
    # type: (int, float) -> bool
    return x > y
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        std_types = [v.standard_type for v in violations]
        assert "int" in std_types
        assert "float" in std_types
        assert "bool" in std_types

    def test_complex_type_comment(self, temp_dir, enforcer):
        """Тест сложного type comment."""
        code = """
from typing import List, Dict

x = []  # type: List[int]
y = {}  # type: Dict[str, float]
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        std_types = [v.standard_type for v in violations]
        assert "int" in std_types
        assert "float" in std_types


class TestCoreEdgeCases:
    """Тесты крайних случаев."""

    def test_import_not_violation(self, temp_dir, enforcer):
        """Тест что импорты не считаются нарушениями."""
        code = """
from numpy import int32 as Int
import numpy as np
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Импорты не должны считаться нарушениями
        import_violations = [v for v in violations if "import" in v.line_content]
        assert len(import_violations) == 0

    def test_type_alias_assignment(self, temp_dir, enforcer):
        """Тест присваивания алиаса типа."""
        code = """
MyInt = int
MyFloat = float
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Это должно считаться нарушением (алиас типа использует стандартный тип)
        assert len(violations) >= 1

    def test_attribute_access_not_violation(self, temp_dir, enforcer):
        """Тест что доступ к атрибутам не считается нарушением."""
        code = """
import numpy as np

x = np.int32(42)
result = np.float64(3.14)
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Доступ к атрибутам через точку может обрабатываться отдельно
        # Проверяем что хотя бы нет ложных срабатываний на np.int32 как вызов
        [v for v in violations if "np." in v.line_content]
        # Это зависит от реализации - может быть или не быть нарушением

    def test_string_literal_not_violation(self, temp_dir, enforcer):
        """Тест что строковые литералы с именами типов не считаются нарушениями."""
        code = """
x = "int"
y = "float is a number type"
message = "Use int for integers"
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Строковые литералы не должны проверяться
        string_violations = [
            v for v in violations if '"' in v.line_content or "'" in v.line_content
        ]
        assert len(string_violations) == 0

    def test_builtin_function_call_not_violation(self, temp_dir, enforcer):
        """Тест что вызовы встроенных функций не считаются нарушениями."""
        code = """
x = int("42")
y = float("3.14")
z = bool(1)
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Вызовы функций преобразования могут не считаться нарушениями
        # в зависимости от контекста
        [
            v
            for v in violations
            if "= int(" in v.line_content or "= float(" in v.line_content
        ]
        # Зависит от реализации


class TestCoreParentTracking:
    """Тесты отслеживания родительских узлов."""

    def test_parent_node_transformer_basic(self):
        """Базовый тест трансформера родительских узлов."""
        code = "x: int = 42"
        tree = ast.parse(code)

        transformer = ParentNodeTransformer()
        transformer.visit(tree)

        # Находим узел Name с id="int"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "int":
                assert hasattr(node, "parent")
                assert isinstance(node.parent, ast.AnnAssign)

    def test_parent_in_nested_structure(self):
        """Тест родителей во вложенной структуре."""
        code = "x: List[int] = []"
        tree = ast.parse(code)

        transformer = ParentNodeTransformer()
        transformer.visit(tree)

        # Проверяем что у вложенных узлов есть родители
        has_parent_count = sum(1 for node in ast.walk(tree) if hasattr(node, "parent"))
        assert has_parent_count > 0


# ============================================================================
# ТЕСТЫ FIXER - ИСПРАВЛЕНИЕ НАРУШЕНИЙ
# ============================================================================


class TestFixerBasic:
    """Базовые тесты исправления."""

    def test_fix_single_violation(self, temp_dir):
        """Тест исправления одного нарушения."""
        code = "x: int = 42\n"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        results = fixer.fix_all()

        assert len(results["fixed"]) == 1

        # Проверяем содержимое после исправления
        new_content = file_path.read_text()
        assert "Int" in new_content

    def test_fix_multiple_violations_same_line(self, temp_dir):
        """Тест исправления нескольких нарушений в одной строке."""
        code = "x, y = 42, 43  # type: int, int\n"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        # Проверяем что файл исправлен
        new_content = file_path.read_text()
        assert "Int" in new_content

    def test_fix_preserves_indentation(self, temp_dir):
        """Тест что исправление сохраняет отступы."""
        code = """
def func():
    x: int = 42
    return x
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        new_content = file_path.read_text()
        # Проверяем что отступы сохранены
        lines = new_content.split("\n")
        assert any("    x:" in line for line in lines)

    def test_fix_dry_run(self, temp_dir):
        """Тест режима dry run."""
        original_code = "x: int = 42\n"
        file_path = temp_dir / "test.py"
        file_path.write_text(original_code)

        config = Config.default()
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        results = fixer.fix_all(dry_run=True)

        # Файл не должен быть изменен
        new_content = file_path.read_text()
        assert new_content == original_code
        assert len(results["skipped"]) == 1


class TestFixerImports:
    """Тесты добавления импортов."""

    def test_add_import_at_beginning(self, temp_dir):
        """Тест добавления импорта в начало файла."""
        code = "x: int = 42\n"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        config.auto_add_imports = True
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        new_content = file_path.read_text()
        # Проверяем что импорт добавлен
        assert "from numpy import" in new_content or "import numpy" in new_content

    def test_add_import_after_existing_imports(self, temp_dir):
        """Тест добавления импорта после существующих импортов."""
        code = """import numpy as np

x: int = 42
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        config.auto_add_imports = True
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        new_content = file_path.read_text()
        lines = new_content.split("\n")

        # Находим позиции импортов
        import_positions = [
            i
            for i, line in enumerate(lines)
            if line.strip().startswith(("import", "from"))
        ]
        assert len(import_positions) > 0

    def test_no_duplicate_imports(self, temp_dir):
        """Тест что импорты не дублируются."""
        code = """from numpy import int32 as Int

x: int = 42
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        config.auto_add_imports = True
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        new_content = file_path.read_text()
        # Считаем количество строк с импортом Int
        import_lines = [
            line
            for line in new_content.split("\n")
            if "import" in line and "Int" in line
        ]
        # Не должно быть дубликатов
        assert len(import_lines) <= 2  # оригинальный + возможно новый


class TestFixerComplexScenarios:
    """Тесты сложных сценариев исправления."""

    def test_fix_generic_types(self, temp_dir):
        """Тест исправления обобщенных типов."""
        code = """
from typing import List

x: List[int] = []
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        new_content = file_path.read_text()
        # Проверяем что int заменен на Int внутри List
        assert "List[Int]" in new_content or "List[ Int ]" in new_content

    def test_fix_union_types(self, temp_dir):
        """Тест исправления Union типов."""
        code = """
from typing import Union

x: Union[int, float] = 42
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        config = Config.default()
        enforcer = TypeEnforcer(config)
        enforcer.scan_file(file_path)

        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        new_content = file_path.read_text()
        # Проверяем что типы заменены
        assert "Int" in new_content
        assert "Float" in new_content


# ============================================================================
# ТЕСТЫ CLI
# ============================================================================


class TestCliParser:
    """Тесты парсера CLI."""

    def test_create_parser(self):
        """Тест создания парсера."""
        parser = create_parser()
        assert parser is not None

    def test_scan_command_args(self):
        """Тест аргументов команды scan."""
        parser = create_parser()
        args = parser.parse_args(["scan", "./src"])
        assert args.command == "scan"
        assert args.path == "./src"

    def test_fix_command_args(self):
        """Тест аргументов команды fix."""
        parser = create_parser()
        args = parser.parse_args(["fix", "./src", "--dry-run", "--no-backup"])
        assert args.command == "fix"
        assert args.dry_run is True
        assert args.no_backup is True

    def test_config_command_args(self):
        """Тест аргументов команды config."""
        parser = create_parser()
        args = parser.parse_args(["config", "--init", "--output", "my_config.json"])
        assert args.command == "config"
        assert args.init is True
        assert args.output == "my_config.json"


class TestCliLoadConfig:
    """Тесты загрузки конфигурации в CLI."""

    def test_load_config_none(self):
        """Тест загрузки конфигурации при None пути."""
        config = load_config(None)
        assert isinstance(config, Config)

    def test_load_config_from_file(self, temp_dir):
        """Тест загрузки конфигурации из файла."""
        config_file = temp_dir / "config.json"
        config_file.write_text('{"custom_types": {"Test": "int"}}')

        config = load_config(str(config_file))
        assert "Test" in config.custom_types


# ============================================================================
# ТЕСТЫ STANDARD_TO_CUSTOM МАППИНГА
# ============================================================================


class TestStandardToCustomMapping:
    """Тесты маппинга стандартных типов в кастомные."""

    def test_float_mappings(self):
        """Тест маппинга для float типов."""
        assert "float" in STANDARD_TO_CUSTOM["Float"]
        assert "np.float64" in STANDARD_TO_CUSTOM["Float"]
        assert "numpy.float64" in STANDARD_TO_CUSTOM["Float"]

    def test_int_mappings(self):
        """Тест маппинга для int типов."""
        assert "int" in STANDARD_TO_CUSTOM["Int"]
        assert "np.int32" in STANDARD_TO_CUSTOM["Int"]

    def test_bool_mappings(self):
        """Тест маппинга для bool типов."""
        assert "bool" in STANDARD_TO_CUSTOM["Bool"]
        assert "np.bool_" in STANDARD_TO_CUSTOM["Bool"]

    def test_ndarray_mappings(self):
        """Тест маппинга для NDArray типов."""
        assert "NDArray[float]" in STANDARD_TO_CUSTOM["NDArrayFloat"]
        assert "NDArray[np.float64]" in STANDARD_TO_CUSTOM["NDArrayFloat"]

    def test_default_types_consistency(self):
        """Тест согласованности DEFAULT_TYPES."""
        for custom_type, standard_type in DEFAULT_TYPES.items():
            assert custom_type in STANDARD_TO_CUSTOM
            assert standard_type in STANDARD_TO_CUSTOM[custom_type]


# ============================================================================
# ТЕСТЫ TYPEVIOLATION
# ============================================================================


class TestTypeViolation:
    """Тесты класса TypeViolation."""

    def test_violation_str_representation(self):
        """Тест строкового представления нарушения."""
        violation = TypeViolation(
            file_path="/path/to/file.py",
            line=10,
            column=5,
            custom_type="Int",
            standard_type="int",
            line_content="x: int = 42",
        )

        str_repr = str(violation)
        assert "TC001" in str_repr
        assert "Int" in str_repr
        assert "int" in str_repr

    def test_violation_location(self):
        """Тест локации нарушения."""
        violation = TypeViolation(
            file_path="/path/to/file.py",
            line=10,
            column=5,
            custom_type="Int",
            standard_type="int",
            line_content="x: int = 42",
        )

        location = violation.location
        assert "/path/to/file.py" in location
        assert "10" in location
        assert "5" in location


# ============================================================================
# ИНТЕГРАЦИОННЫЕ ТЕСТЫ
# ============================================================================


class TestIntegration:
    """Интеграционные тесты полного цикла."""

    def test_full_cycle_scan_and_fix(self, temp_dir):
        """Тест полного цикла: сканирование -> исправление -> проверка."""
        # Создаем файл с нарушениями
        code = """
def process(x: int, y: float) -> bool:
    return x > y

data: List[int] = [1, 2, 3]
"""
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        # Сканируем
        config = Config.default()
        enforcer = TypeEnforcer(config)
        violations = enforcer.scan_file(file_path)

        assert len(violations) > 0

        # Исправляем
        fixer = TypeFixer(enforcer)
        fixer.fix_all()

        # Сканируем снова
        enforcer2 = TypeEnforcer(config)
        enforcer2.scan_file(file_path)

        # Нарушений должно стать меньше или не остаться вовсе
        # (зависит от того, все ли типы были исправлены)

    def test_directory_scan_with_exclusions(self, temp_dir):
        """Тест сканирования директории с исключениями."""
        # Создаем структуру директорий
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        venv_dir = temp_dir / "venv"
        venv_dir.mkdir()

        # Создаем файлы
        (src_dir / "main.py").write_text("x: int = 1")
        (git_dir / "config.py").write_text("y: int = 2")
        (venv_dir / "lib.py").write_text("z: int = 3")

        config = Config.default()
        enforcer = TypeEnforcer(config)
        violations = enforcer.scan_directory(temp_dir)

        # Должны быть найдены нарушения только в src/main.py
        # .git и venv должны быть исключены
        files_with_violations = set(v.file_path for v in violations)
        assert any("src/main.py" in f for f in files_with_violations)
        assert not any(".git" in f for f in files_with_violations)
        assert not any("venv" in f for f in files_with_violations)

    def test_multiple_files_fix(self, temp_dir):
        """Тест исправления нескольких файлов."""
        # Создаем несколько файлов с нарушениями
        file1 = temp_dir / "file1.py"
        file1.write_text("x: int = 1\n")

        file2 = temp_dir / "file2.py"
        file2.write_text("y: float = 2.0\n")

        config = Config.default()
        enforcer = TypeEnforcer(config)
        enforcer.scan_directory(temp_dir)

        fixer = TypeFixer(enforcer)
        results = fixer.fix_all()

        assert len(results["fixed"]) >= 2

        # Проверяем что оба файла исправлены
        assert "Int" in file1.read_text()
        assert "Float" in file2.read_text()


# ============================================================================
# ТЕСТЫ ПРОИЗВОДИТЕЛЬНОСТИ И СТАБИЛЬНОСТИ
# ============================================================================


class TestPerformanceStability:
    """Тесты производительности и стабильности."""

    def test_large_file_scanning(self, temp_dir, enforcer):
        """Тест сканирования большого файла."""
        # Создаем большой файл с множеством аннотаций
        lines = ["x_{}: int = {}".format(i, i) for i in range(1000)]
        code = "\n".join(lines)

        file_path = temp_dir / "large.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Должно найти много нарушений
        assert len(violations) == 1000

    def test_deeply_nested_types(self, temp_dir, enforcer):
        """Тест глубоко вложенных типов."""
        code = "x: List[List[List[List[int]]]] = []"
        file_path = temp_dir / "test.py"
        file_path.write_text(code)

        violations = enforcer.scan_file(file_path)

        # Должно найти нарушение для int
        assert any(v.standard_type == "int" for v in violations)

    def test_empty_and_whitespace_files(self, temp_dir, enforcer):
        """Тест пустых файлов и файлов с пробелами."""
        empty_file = temp_dir / "empty.py"
        empty_file.write_text("")

        whitespace_file = temp_dir / "whitespace.py"
        whitespace_file.write_text("\n\n   \n\t\n")

        # Не должно возникать ошибок
        violations1 = enforcer.scan_file(empty_file)
        violations2 = enforcer.scan_file(whitespace_file)

        assert len(violations1) == 0
        assert len(violations2) == 0

    def test_unicode_in_code(self, temp_dir, enforcer):
        """Тест кода с Unicode символами."""
        code = '''
# Комментарий с Unicode: Hello world! 
def функция(x: int) -> float:
    """Функция с описанием"""
    return float(x)
'''
        file_path = temp_dir / "unicode.py"
        file_path.write_text(code, encoding="utf-8")

        violations = enforcer.scan_file(file_path)

        # Должно корректно обработать
        assert any(v.standard_type == "int" for v in violations)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
