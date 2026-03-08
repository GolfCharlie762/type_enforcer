"""Тест для проверки относительных импортов."""
from ...types import Bool, Float, Int, NDArrayFloat
from numpy import int32 as Int
from numpy import float64 as Float

def test_function(a: Int, b: Float) -> Float:
    """Функция с типами."""
    return float(a) * b
