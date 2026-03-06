"""Модуль конфигурации для Type Enforcer."""

import json
import os
from pathlib import Path
from typing import Dict, List, Union, Optional
from dataclasses import dataclass, asdict, field

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
    # По умолчанию используется "src/types.py"
    types_file: Union[str, List[str], None] = "src/types.py"

    # Использовать относительные импорты (True) или абсолютные (False)
    # True: from .types import NDArrayFloat
    # False: from src.types import NDArrayFloat
    relative_import: bool = True

    # Пути для игнорирования
    exclude_paths: List[str] = None

    # Расширения файлов для проверки
    extensions: List[str] = None

    # Автоматически добавлять импорты при фиксе
    auto_add_imports: bool = True

    # Резервное копирование при фиксе
    backup_files: bool = True
    
    # Словарь для хранения загруженных типов из файлов (имя типа -> модуль)
    _type_to_module: Dict[str, str] = field(default_factory=dict, repr=False)

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
                # Файл не найден, пропускаем (не ошибка, т.к. может быть создан позже)
                continue
            
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
                    # Если нет именованного словаря, ищем все определения типов
                    # (переменные, которые являются алиасами типов)
                    for attr_name in dir(module):
                        if attr_name.startswith('_'):
                            continue
                        attr = getattr(module, attr_name)
                        # Проверяем, является ли атрибут потенциальным типом
                        if isinstance(attr, type) or hasattr(attr, '__module__'):
                            # Это класс или тип
                            self.custom_types[attr_name] = attr_name
                            self._type_to_module[attr_name] = str(path)
                        elif isinstance(attr, dict) and attr_name.isupper():
                            # Словарь с типами
                            self.custom_types.update(attr)
                            for type_name in attr.keys():
                                self._type_to_module[type_name] = str(path)
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
        return cls(
            custom_types=DEFAULT_TYPES.copy(),
            types_file="src/types.py",
            relative_import=True
        )

    def get_import_for_type(self, type_name: str, current_file_path: Union[str, Path]) -> Optional[str]:
        """
        Получить строку импорта для указанного типа.
        
        Args:
            type_name: Имя типа (например, NDArrayFloat)
            current_file_path: Путь к файлу, в который нужно добавить импорт
            
        Returns:
            Строка импорта или None, если тип не найден
        """
        if type_name not in self._type_to_module:
            # Тип не загружен из файла, пробуем стандартные импорты
            return DEFAULT_IMPORTS.get(type_name)
        
        types_file_path = Path(self._type_to_module[type_name]).resolve()
        current_path = Path(current_file_path).resolve()
        
        # Определяем имя модуля (без расширения .py)
        module_name = types_file_path.stem  # например, 'types' из 'types.py'
        
        if self.relative_import:
            # Вычисляем относительный путь от текущего файла до файла с типами
            try:
                # Получаем относительный путь между директориями
                rel_path = os.path.relpath(types_file_path.parent, current_path.parent)
                
                # Если файл в той же директории
                if rel_path == '.':
                    return f"from .{module_name} import {type_name}"
                
                # Преобразуем путь в формат импорта
                # .. означает подъем на уровень вверх, обычные части - спуск вниз
                parts = rel_path.split(os.sep)
                
                # Считаем количество уровней вверх
                up_levels = len([p for p in parts if p == '..'])
                down_parts = [p for p in parts if p != '..']
                
                # Формируем строку импорта
                # Если есть подъемы вверх (up_levels > 0), используем относительный импорт с точками
                # Если нет подъемов (up_levels == 0), но есть down_parts - это абсолютный путь внутри проекта
                if up_levels > 0:
                    dots = '.' * (up_levels + 1)
                    if down_parts:
                        module_path = '.'.join(down_parts)
                        return f"from {dots}{module_path}.{module_name} import {type_name}"
                    else:
                        return f"from {dots}{module_name} import {type_name}"
                else:
                    # Нет подъемов вверх - значит файл с типами находится в поддереве
                    # Это должен быть абсолютный импорт внутри проекта
                    pass  # Переходим к абсолютному импорту
            except Exception:
                # Не удалось получить относительный путь, используем абсолютный
                pass
        
        # Абсолютный импорт
        # Пытаемся определить корневой модуль (предполагаем, что это первая директория в пути)
        try:
            # Для пути src/types.py -> from src.types import Type
            # Используем относительный путь от рабочей директории
            try:
                rel_to_cwd = types_file_path.relative_to(Path.cwd())
                parts = rel_to_cwd.parts
            except ValueError:
                # Если файл не внутри CWD, используем полный путь
                parts = types_file_path.parts
            
            if len(parts) >= 2:
                root_module = parts[0]
                remaining_parts = parts[1:-1]  # все части кроме последней (файл)
                if remaining_parts:
                    module_path = '.'.join([root_module] + list(remaining_parts))
                    return f"from {module_path}.{module_name} import {type_name}"
                else:
                    return f"from {root_module}.{module_name} import {type_name}"
        except Exception:
            pass
        
        # Фолбэк: просто имя модуля
        return f"from {module_name} import {type_name}"
