"""Модуль с кастомными типами данных."""

from numpy.typing import NDArray
from numpy import float64 as Float
from numpy import int32 as Int
from numpy import uint32 as Uint
from numpy import bool_ as Bool
from numpy import longdouble as LongDouble

# Скалярные типы
NDArrayFloat = NDArray[Float]
NDArrayInt = NDArray[Int]
NDArrayUint = NDArray[Uint]
NDArrayBool = NDArray[Bool]

# Словарь типов для экспорта
TYPES = {
    "Float": "float",
    "Int": "int",
    "Uint": "uint",
    "Bool": "bool",
    "LongDouble": "longdouble",
    "NDArray": "ndarray",
    "NDArrayFloat": "NDArray[float]",
    "NDArrayInt": "NDArray[int]",
    "NDArrayUint": "NDArray[uint]",
    "NDArrayBool": "NDArray[bool]",
}
