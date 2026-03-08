#ignore-type - этот файл не должен проверяться линтером
"""Тест для проверки работы ignore-type на уровне файла."""
import numpy as np

def test_function(n_temp: np.ndarray) -> float:
    """Функция с float."""
    n: float = float(n_temp.item()) if not np.isnan(n_temp).any() else np.nan
    return n
