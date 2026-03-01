"""
Тестовый файл для проверки базовых типов.
Должен содержать нарушения (использование стандартных типов вместо кастомных).
"""

from typing import List, Dict, Optional, Union, Any
import numpy as np
from numpy import float64 as Float
from numpy import int32 as Int

# ========== ПЕРЕМЕННЫЕ ==========

# Правильно (не должно быть нарушений)
correct_int: Int = 42
correct_float: Float = 3.14159
correct_bool: Bool = True
correct_uint: Uint = 100
correct_long_double: LongDouble = 1.23456789012345

# Неправильно (ДОЛЖНЫ быть нарушения)
wrong_int: Int = 42
wrong_float: Float = 3.14159
wrong_bool: Bool = True
wrong_uint: Int = 100  # должно быть Uint
wrong_long_double: Float = 1.23456789012345  # должно быть LongDouble


# ========== ФУНКЦИИ ==========

# Правильная функция
def correct_function(
        a: Int,
        b: Float,
        c: Bool = True
) -> Float:
    """Функция с правильными типами."""
    result = Float(a) * b
    if c:
        return result
    return Float(0.0)


# Неправильная функция (нарушения в аргументах и возврате)
def wrong_function(
        a: Int,  # нарушение
        b: Float,  # нарушение
        c: Bool = True  # нарушение
) -> Float:  # нарушение
    """Функция с неправильными типами."""
    result = Float(a) * b
    if c:
        return result
    return 0.0


# ========== КЛАССЫ ==========

class CorrectClass:
    """Класс с правильными типами."""

    def __init__(self, value: Int, name: str):
        self.value = value
        self.name = name
        self.flag: Bool = True

    def process(self, multiplier: Float) -> Float:
        """Метод с правильными типами."""
        return Float(self.value) * multiplier

    @property
    def is_positive(self) -> Bool:
        """Свойство с правильным типом."""
        return self.value > 0


class WrongClass:
    """Класс с неправильными типами."""

    def __init__(self, value: Int, name: str):  # нарушение
        self.value = value
        self.name = name
        self.flag: Bool = True  # нарушение

    def process(self, multiplier: Float) -> Float:  # нарушения
        """Метод с неправильными типами."""
        return Float(self.value) * multiplier

    @property
    def is_positive(self) -> Bool:  # нарушение
        """Свойство с неправильным типом."""
        return self.value > 0


# ========== СЛОЖНЫЕ АННОТАЦИИ ==========

# Правильные сложные типы
correct_list: List[Int] = [1, 2, 3, 4, 5]
correct_dict: Dict[str, Float] = {"pi": 3.14, "e": 2.71}
correct_optional: Optional[Bool] = None
correct_union: Union[Int, Float, str] = 42
correct_any: Any = "можно anything"

# Неправильные сложные типы
wrong_list: List[int] = [1, 2, 3, 4, 5]  # нарушение
wrong_dict: Dict[str, Float] = {"pi": 3.14, "e": 2.71}  # нарушение
wrong_optional: Optional[bool] = None  # нарушение
wrong_union: Union[Int, Float, str] = 42  # нарушения (int и float)

# ========== ВЛОЖЕННЫЕ ТИПЫ ==========

# Правильные вложенные типы
correct_nested_list: List[List[Int]] = [[1, 2], [3, 4]]
correct_nested_dict: Dict[str, List[Float]] = {
    "first": [1.1, 1.2],
    "second": [2.1, 2.2]
}
correct_complex: Dict[str, Union[Int, List[Float]]] = {
    "simple": 42,
    "complex": [1.1, 1.2]
}

# Неправильные вложенные типы
wrong_nested_list: List[List[int]] = [[1, 2], [3, 4]]  # нарушение
wrong_nested_dict: Dict[str, List[float]] = {  # нарушение
    "first": [1.1, 1.2],
    "second": [2.1, 2.2]
}
wrong_complex: Dict[str, Union[Int, List[float]]] = {  # нарушения
    "simple": 42,
    "complex": [1.1, 1.2]
}