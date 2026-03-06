"""Модуль конфигурации для Type Enforcer."""

import json
from pathlib import Path
from typing import Dict, List, Union
from dataclasses import dataclass, asdict

# Типы по умолчанию из запроса
DEFAULT_TYPES = {
    # Кастомный тип -> стандартный тип
    "Float": "float",
    "Int": "int",
    "Uint": "uint",
    "LongDouble": "float",
    "Bool": "bool",
    "NDArrayFloat": "NDArray",
    "NDArrayInt": "NDArray",
    "NDArrayUint": "NDArray",
    "NDArrayBool": "NDArray",
}

# Импорты, которые нужно добавлять
DEFAULT_IMPORTS = {
    "Float": "from numpy import float64 as Float",
    "Int": "from numpy import int32 as Int",
    "Uint": "from numpy import uint32 as Uint",
    "LongDouble": "from numpy import longdouble as LongDouble",
    "Bool": "bool",  # стандартный bool
    "NDArrayFloat": "from numpy.typing import NDArray\nfrom numpy import float64 as Float",
    "NDArrayInt": "from numpy.typing import NDArray\nfrom numpy import int32 as Int",
    "NDArrayUint": "from numpy.typing import NDArray\nfrom numpy import uint32 as Uint",
    "NDArrayBool": "from numpy.typing import NDArray\nfrom numpy import bool_",
}


@dataclass
class Config:
    """Конфигурация для Type Enforcer."""

    # Типы для проверки
    custom_types: Dict[str, str] = None

    # Путь к файлу с кастомными типами (может быть строкой или списком путей)
    types_file: Union[str, List[str], None] = None

    # Пути для игнорирования
    exclude_paths: List[str] = None

    # Расширения файлов для проверки
    extensions: List[str] = None

    # Автоматически добавлять импорты при фиксе
    auto_add_imports: bool = True

    # Резервное копирование при фиксе
    backup_files: bool = True

    def __post_init__(self):
        if self.custom_types is None:
            self.custom_types = {}
        
        # Загружаем типы из файла, если указан
        if self.types_file is not None:
            self._load_types_from_file()
        
        if self.exclude_paths is None:
            self.exclude_paths = [".git", "__pycache__", "venv", "env", ".env"]
        if self.extensions is None:
            self.extensions = [".py"]

    def _load_types_from_file(self):
        """Загрузить кастомные типы из указанного файла (или файлов)."""
        files_to_load = []
        
        if isinstance(self.types_file, str):
            files_to_load = [self.types_file]
        elif isinstance(self.types_file, list):
            files_to_load = self.types_file
        
        for file_path in files_to_load:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"Файл с типами не найден: {file_path}")
            
            # Поддерживаем разные форматы файлов с типами
            if path.suffix == '.json':
                with open(path, 'r', encoding='utf-8') as f:
                    loaded_types = json.load(f)
                    self.custom_types.update(loaded_types)
            elif path.suffix == '.py':
                # Загружаем типы из Python файла (ожиается словарь TYPES или CUSTOM_TYPES)
                import importlib.util
                spec = importlib.util.spec_from_file_location("custom_types_module", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Ищем словарь с типами в модуле
                if hasattr(module, 'TYPES'):
                    self.custom_types.update(module.TYPES)
                elif hasattr(module, 'CUSTOM_TYPES'):
                    self.custom_types.update(module.CUSTOM_TYPES)
                else:
                    # Если нет именованного словаря, ищем первый словарь в модуле
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, dict) and attr_name.isupper():
                            self.custom_types.update(attr)
                            break
            else:
                raise ValueError(f"Неподдерживаемый формат файла с типами: {path.suffix}")

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "Config":
        """Загрузить конфигурацию из файла."""
        path = Path(path)
        if path.suffix == ".json":
            with open(path, "r") as f:
                data = json.load(f)
            return cls(**data)
        else:
            # Поддержка других форматов можно добавить позже
            raise ValueError(f"Unsupported config format: {path.suffix}")

    def to_file(self, path: Union[str, Path]):
        """Сохранить конфигурацию в файл."""
        path = Path(path)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def default(cls) -> "Config":
        """Создать конфигурацию по умолчанию."""
        return cls(custom_types=DEFAULT_TYPES.copy())
