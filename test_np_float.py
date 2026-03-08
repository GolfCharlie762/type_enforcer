"""Тест для проверки работы с np.float64."""
import numpy as np
from typing import Optional
from numpy import float64 as Float

def test_function(n_temp: np.ndarray) -> Float:
    """Функция с np.Float."""
    n: Float = float(n_temp.item()) if not np.isnan(n_temp).any() else np.nan
    return n
