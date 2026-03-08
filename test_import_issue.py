"""Тест для проверки проблемы с импортами."""
from ...types import Float, Int
from numpy import float64 as Float
from numpy import int32 as Int

def test_function(a: Int) -> Float:
    """Функция с типами."""
    return float(a)
