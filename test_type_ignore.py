"""Тестовый файл для проверки type: ignore."""

from typing import List, Dict, Optional, Union

# Неправильно (ДОЛЖНЫ быть нарушения)
wrong_int: int = 42
wrong_float: float = 3.14159

# С type: ignore (НЕ должно быть нарушений)
ignored_int: int = 42  # type: ignore
ignored_float: float = 3.14159  # type: ignore

# С type: ignore в разных форматах
ignored_with_space: int = 100  #type: ignore
ignored_with_comment: int = 200  # type: ignore # это комментарий

# Функция с type: ignore
def wrong_function(
    a: int,  # нарушение
    b: float,  # нарушение
) -> float:  # нарушение
    return float(a) * b

def ignored_function(
    a: int,  # type: ignore
    b: float,  # type: ignore
) -> float:  # type: ignore
    return float(a) * b

# Частичный ignore - только некоторые строки игнорируются
partial_list: List[int] = [1, 2, 3]  # нарушение внутри аннотации
partial_ignored: List[int] = [1, 2, 3]  # type: ignore
