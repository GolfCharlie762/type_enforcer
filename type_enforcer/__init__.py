"""Type Enforcer - библиотека для проверки использования кастомных типов данных."""

from .core import TypeEnforcer
from .config import Config, DEFAULT_TYPES

__version__ = "0.1.0"
__all__ = ["TypeEnforcer", "Config", "DEFAULT_TYPES"]