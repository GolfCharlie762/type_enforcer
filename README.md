# Type Enforcer

Инструмент для автоматической проверки и приведения типов в Python-проектах с поддержкой кастомных типов (например, алиасов NumPy).

## Возможности

- ✅ Автоматическая проверка типов в аннотациях функций и переменных
- ✅ Поддержка кастомных типов через внешний файл конфигурации
- ✅ Автогенерация правильных импортов (относительных или абсолютных)
- ✅ Гибкая настройка через JSON-конфиг
- ✅ Интеграция в CLI

---

## Установка

```bash
pip install -e .
```

Или используйте напрямую из репозитория:

```bash
python -m type_enforcer ...
```

---

## Быстрый старт

### 1. Инициализация конфигурации

Создайте базовый конфиг в текущей директории:

```bash
type-enforcer config --init
```

Это создаст файл `type_enforcer_config.json` со следующими настройками по умолчанию:

```json
{
  "custom_types": {},
  "types_file": "src/types.py",
  "relative_import": true,
  "exclude_patterns": ["**/__pycache__/**", "**/.git/**"],
  "strict_mode": false
}
```

### 2. Создание файла с кастомными типами

Создайте файл, указанный в параметре `types_file` (по умолчанию `src/types.py`):

```python
# src/types.py
import numpy as np
from numpy.typing import NDArray

# Базовые алиасы
Float = np.float64
LongDouble = np.longdouble
Int = np.int32
Uint = np.uint32
Bool = bool

# Алиасы для массивов
NDArrayFloat = NDArray[Float]
NDArrayInt = NDArray[Int]
NDArrayUint = NDArray[Uint]
NDArrayBool = NDArray[np.bool_]
```

> **Важно:** Типы должны быть объявлены как присваивания на верхнем уровне модуля (например, `MyType = SomeBase`).

### 3. Запуск проверки

Запустите проверку типов в вашем проекте:

```bash
type-enforcer check src/
```

Или проверьте конкретный файл:

```bash
type-enforcer check src/main.py
```

Если в коде используется тип `NDArrayFloat`, но забыт импорт, инструмент автоматически предложит или добавит правильный импорт в зависимости от настроек.

---

## Конфигурация

Файл конфигурации `type_enforcer_config.json` поддерживает следующие поля:

| Поле | Тип | Описание | По умолчанию |
|------|-----|----------|--------------|
| `types_file` | `str` или `list[str]` | Путь(и) к файлу(ам) с кастомными типами | `"src/types.py"` |
| `relative_import` | `bool` | Использовать относительные импорты (`from .types import ...`) вместо абсолютных (`from src.types import ...`) | `true` |
| `custom_types` | `dict` | Дополнительные типы, заданные вручную (если не используются файлы) | `{}` |
| `exclude_patterns` | `list[str]` | Шаблоны путей для исключения из проверки (glob) | `["**/__pycache__/**"]` |
| `strict_mode` | `bool` | Строгий режим: ошибка при любом несоответствии типов | `false` |

### Пример расширенной конфигурации

```json
{
  "types_file": ["src/types.py", "src/extra_types.py"],
  "relative_import": false,
  "custom_types": {
    "Vector": "List[float]"
  },
  "exclude_patterns": [
    "**/__pycache__/**",
    "**/tests/**",
    "**/legacy/**"
  ],
  "strict_mode": true
}
```

---

## Как работают импорты

Инструмент автоматически определяет, какой импорт добавить в файл, основываясь на расположении файла с типами и файла, где тип используется.

### Относительные импорты (`relative_import: true`)

- Если файл с типами находится в той же папке:  
  `from .types import NDArrayFloat`
- Если файл с типами на уровень выше:  
  `from ..types import NDArrayFloat`
- Если файл с типами в соседней ветке:  
  `from ...module.types import NDArrayFloat`

### Абсолютные импорты (`relative_import: false`)

Всегда генерируется полный путь от корня проекта:  
`from src.types import NDArrayFloat`

> Убедитесь, что ваш проект является пакетом (имеет `__init__.py`), если используете относительные импорты.

---

## CLI команды

### `config --init`

Создаёт новый файл конфигурации в текущей директории.

```bash
type-enforcer config --init
```

### `check <path>`

Проверяет указанные файлы или директории на соответствие типам.

```bash
type-enforcer check src/
type-enforcer check src/main.py src/utils.py
```

Опции:
- `--fix` — автоматически исправлять отсутствующие импорты (если возможно)
- `--verbose` — подробный вывод
- `--config <path>` — указать путь к конфигу (по умолчанию ищет `type_enforcer_config.json`)

Пример:

```bash
type-enforcer check src/ --fix --verbose
```

### `types --list`

Выводит список всех загруженных кастомных типов из конфига и файлов.

```bash
type-enforcer types --list
```

---

## Структура проекта (пример)

```
my_project/
├── type_enforcer_config.json
├── src/
│   ├── __init__.py
│   ├── types.py          # Файл с кастомными типами
│   ├── main.py           # Использует NDArrayFloat
│   └── utils/
│       ├── __init__.py
│       └── helpers.py    # Тоже использует типы
└── tests/
    └── test_main.py
```

В `src/main.py`:

```python
# До запуска type-enforcer
def process(data):  # ❌ Нет аннотации
    ...

# После запуска с --fix
from .types import NDArrayFloat  # ✅ Добавлено автоматически

def process(data: NDArrayFloat) -> NDArrayFloat:
    ...
```

---

## Требования

- Python 3.8+
- Библиотеки (опционально, в зависимости от типов):
  - `numpy`
  - `typing_extensions`

---

## Лицензия

MIT