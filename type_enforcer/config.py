"""Модуль конфигурации для Type Enforcer."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Union
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
    custom_types: Dict[str, str]

    # Пути для игнорирования
    exclude_paths: List[str] = None

    # Расширения файлов для проверки
    extensions: List[str] = None

    # Автоматически добавлять импорты при фиксе
    auto_add_imports: bool = True

    # Резервное копирование при фиксе
    backup_files: bool = True

    def __post_init__(self):
        if self.exclude_paths is None:
            self.exclude_paths = [".git", "__pycache__", "venv", "env", ".env"]
        if self.extensions is None:
            self.extensions = [".py"]

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