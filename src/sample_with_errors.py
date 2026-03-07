"""Файл с ошибками для тестирования."""

import numpy as np
from typing import List, Union, Optional

def process_data(x: int, y: float) -> bool:
    """Обработка данных."""
    return x > 0

class DataProcessor:
    def __init__(self, value: int):
        self.value = value
    
    def process(self, arr: List[float]) -> Union[int, float]:
        return sum(arr)

optional_value: Optional[bool] = None
array_data: NDArray[float] = np.array([1.0, 2.0])
