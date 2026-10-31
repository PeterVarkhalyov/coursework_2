# Курсовая работа 2

## Вступление

Учебное консольное приложение на Python, которое:

1. получает координаты и прямоугольные границы выбранных стран через Nominatim API;
2. передаёт эти границы в OpenSky API;
3. получает воздушные суда, находящиеся внутри найденных областей;
4. выводит результат в JSON.

Проект использует только стандартную библиотеку Python для выполнения HTTP-запросов. 
OpenSky API работает в анонимном режиме, без логина и пароля.

## Требования

- Python 3.12 или новее;
- Poetry 2.x — для установки dev-зависимостей и запуска проверок;
- доступ к интернету во время получения данных из API.

## Установка

Клонируйте проект и перейдите в его каталог:

```powershell
git clone <адрес-репозитория>
cd coursework_2
```

Установите зависимости:

```powershell
poetry install --no-root
```

Приложение не имеет обязательных сторонних runtime-зависимостей. Poetry устанавливает инструменты разработки:
`pytest`, `pytest-cov`, `flake8`, `mypy`, `isort` и `black`.

## Запуск

Передайте названия стран позиционными аргументами:

```powershell
poetry run python -m src Россия Германия
```

Если страны не переданы, программа запросит их интерактивно:

```powershell
poetry run python -m src
```

Пример ввода:

```text
Введите страны через запятую: Россия, Германия
```

### Сохранение результата

Для сохранения JSON в файл используйте `--output` или `-o`:

```powershell
poetry run python -m src Россия -o result.json
```

### Включение наземных объектов

По умолчанию записи, отмеченные OpenSky как находящиеся на земле, исключаются. Чтобы включить их:

```powershell
poetry run python -m src Россия --include-ground
```

Все параметры CLI:

```powershell
poetry run python -m src --help
```

## Переменные окружения

Настройки API можно переопределить переменными окружения:

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `NOMINATIM_BASE_URL` | `https://nominatim.openstreetmap.org` | Адрес Nominatim API |
| `NOMINATIM_USER_AGENT` | `coursework-2-airspace/1.0` | Идентификатор приложения |
| `OPENSKY_BASE_URL` | `https://opensky-network.org/api` | Адрес OpenSky API |

Пример для PowerShell:

```powershell
$env:NOMINATIM_USER_AGENT = "airspace-study/1.0 (contact: email@example.com)"
poetry run python -m src Россия
```

Для публичного Nominatim рекомендуется указывать уникальный `User-Agent` с контактной информацией владельца
приложения.

## Формат результата

Программа возвращает JSON следующей структуры:

```json
{
  "attribution": [
    "Geocoding © OpenStreetMap contributors, ODbL 1.0",
    "Aircraft data © The OpenSky Network"
  ],
  "countries": [
    {
      "country": {
        "name": "Россия",
        "country_code": "RU",
        "latitude": 64.6863136,
        "longitude": 97.7453061,
        "bounding_box": {
          "south": 41.1850968,
          "north": 82.0586232,
          "west": -180.0,
          "east": 180.0
        }
      },
      "aircraft": [
        {
          "icao24": "abc123",
          "callsign": "TEST1",
          "origin_country": "Russian Federation",
          "time_position": 1793450000,
          "last_contact": 1793450005,
          "longitude": 37.6176,
          "latitude": 55.7558,
          "baro_altitude": 10000.0,
          "on_ground": false,
          "velocity": 230.0,
          "true_track": 90.0,
          "vertical_rate": 1.5,
          "sensors": [1, 2],
          "geo_altitude": 10100.0,
          "squawk": "7000",
          "spi": false,
          "position_source": 0
        }
      ]
    }
  ]
}
```

Значения некоторых полей могут быть `null`, если OpenSky не располагает соответствующими данными.

## Архитектура

Поток данных:

```text
Названия стран
      ↓
NominatimAPI
      ↓
CountryCoordinates + BoundingBox
      ↓
OpenSkyAPI
      ↓
list[AircraftState]
      ↓
AirspaceCollector
      ↓
list[CountryAirspace]
      ↓
JSON
```

Основные классы:

- `AbstractAPIClient` — абстрактный родительский класс и общий HTTP-метод;
- `NominatimAPI` — поиск страны, получение координат и границ;
- `OpenSkyAPI` — получение и разбор state vectors воздушных судов;
- `AirspaceCollector` — объединение данных Nominatim и OpenSky;
- `BoundingBox` — прямоугольные географические границы;
- `CountryCoordinates` — сведения о стране;
- `AircraftState` — состояние одного воздушного судна;
- `CountryAirspace` — итоговые данные по одной стране.

## Структура проекта

```text
coursework_2/
├── configs/
├── data/
├── htmlcov/
├── logs/
├── src/
│   ├── __init__.py
│   ├── api.py
│   ├── models.py
│   └── service.py
├── tests/
│   ├── test_api.py
│   ├── test_models.py
│   └── test_service.py
├── .coverage
├── .flake8
├── .gitignore
├── pyproject.toml
├── poetry.lock
└── README.md
```

### Модуль `__init__.py`

Модуль отмечает каталог `src` как пакет Python и определяет его публичный интерфейс. Он импортирует основные
классы из остальных модулей, благодаря чему их можно получать непосредственно из пакета:

```python
from src import AirspaceCollector, NominatimAPI, OpenSkyAPI
```

Список `__all__` содержит имена, которые считаются публичной частью проекта:

- `APIError` и `AbstractAPIClient`;
- клиенты `NominatimAPI` и `OpenSkyAPI`;
- модели `BoundingBox`, `CountryCoordinates`, `AircraftState` и `CountryAirspace`;
- сервис `AirspaceCollector`.


### Модуль `models.py`

Модуль содержит dataclass-модели, описывающие данные приложения. Он не обращается к внешним API и не зависит от
формата пользовательского ввода.

Модели позволяют передавать между слоями программы типизированные объекты вместо необработанных JSON-словарей и
массивов.

#### Class `BoundingBox`

Хранит южную, северную, западную и восточную границы. 

##### Метод `__post_init__()` 

Проверяет диапазоны  широты и долготы.

##### Метод `contains()` 

Определяет попадание точки в прямоугольник.

##### Метод `to_query_params()` 

Формирует  параметры `lamin`, `lamax`, `lomin` и `lomax` для OpenSky.

#### Class `CountryCoordinates` 

Хранит название страны, код ISO, координаты центральной точки и объект `BoundingBox`.

#### Class `AircraftState` 

Представляет `state vector` одного воздушного судна. 
Модель содержит:
- идентификатор ICAO24,
- позывной, 
- страну регистрации, 
- координаты, 
- высоту, 
- скорость, 
- курс, 
- данные сенсоров 
- состояние транспондера.

Поля с типом `... | None` могут отсутствовать в ответе OpenSky.
 
#### Class `CountryAirspace` 

Объединяет сведения о стране и список найденных в её прямоугольных границах воздушных судов.

### Модуль `api.py`

Модуль отвечает за сетевое взаимодействие с Nominatim и OpenSky, проверку ответов и преобразование JSON в модели
из `models.py`. HTTP-запросы выполняются средствами стандартной библиотеки Python.

#### Class `APIError` 

Единый тип исключения для ошибок соединения, HTTP-ответов и некорректных данных.


#### Class `AbstractAPIClient` 

Абстрактный родительский класс. Он хранит базовый URL и тайм-аут, требует реализацию метода `connect()` и предоставляет 
общий метод `_request_json()` для GET-запросов и разбора JSON.

#### Class `NominatimAPI` 

Получает центральные координаты, ISO-код и прямоугольные границы страны. 
Клиент передаёт обязательный `User-Agent`, выдерживает интервал между запросами не менее одной секунды и хранит найденные страны
  во внутреннем кэше на время работы программы.
  
#### Class `OpenSkyAPI` 

Запрашивает endpoint `states/all` по границам `BoundingBox`, преобразует массивы OpenSky в объекты `AircraftState`, исключает 
некорректные записи и при необходимости удаляет объекты, находящиеся на земле.

Вспомогательные методы `_to_float()`, `_to_int()` и `_to_int_list()` безопасно преобразуют необязательные значения
из ответа OpenSky. Если значение отсутствует или имеет неподходящий формат, они возвращают `None`.

Сетевые исключения `HTTPError`, `URLError`, `TimeoutError` и ошибки разбора JSON преобразуются в `APIError`, чтобы
вызывающий код мог обрабатывать все проблемы API единообразно.

### Модуль `service.py`

Модуль содержит сервисный слой `AirspaceCollector`, который связывает клиентов Nominatim и OpenSky. Клиенты
передаются через конструктор и сохраняются в атрибутах `nominatim` и `opensky`.

Метод `collect()` выполняет следующую последовательность:

1. удаляет пробелы из названий стран и исключает пустые значения;
2. запрашивает через `NominatimAPI` координаты и `BoundingBox` каждой страны;
3. передаёт границы в `OpenSkyAPI`;
4. получает список объектов `AircraftState`;
5. объединяет страну и воздушные суда в объект `CountryAirspace`;
6. возвращает список результатов для всех выбранных стран.

Параметр `airborne_only` передаётся клиенту OpenSky и позволяет исключить наземные объекты. Если после очистки не
осталось ни одного названия страны, метод выбрасывает `ValueError`.

## Тестирование

Запуск всех тестов:

```powershell
poetry run pytest
```

Настройки `pytest` автоматически включают измерение строк и ветвей кода и требуют покрытие не ниже 100%.
Текущий результат:

```text
67 passed
Statements: 100%
Branches:   100%
Total:      100%
```

Тесты не выполняют реальные запросы к Nominatim и OpenSky. Сетевые ответы и ошибки имитируются.

## Проверка качества кода

```powershell
poetry run flake8 src tests
poetry run mypy src tests
poetry run isort --check-only src tests
poetry run black --check src tests
```

## Ограничения

- OpenSky фильтрует данные по прямоугольнику `BoundingBox`, а не по точной государственной границе. Поэтому в
  результат могут попасть воздушные суда над соседними территориями или морями.
- `origin_country` означает страну, определённую по ICAO24-адресу транспондера, а не страну текущего положения.
- Анонимные запросы OpenSky имеют ограничения по квоте и частоте.
- Наличие воздушного судна в ответе зависит от покрытия OpenSky и доступности актуальных координат.
- Кэш Nominatim хранится только в памяти и очищается после завершения программы.
- Клиент выдерживает интервал не менее одной секунды между запросами к публичному Nominatim.

## Используемые API

- [Nominatim Search API](https://nominatim.org/release-docs/latest/api/Search/)
- [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/)
- [OpenSky REST API](https://openskynetwork.github.io/opensky-api/rest.html)

При изменении или публикации проекта необходимо соблюдать условия использования и требования атрибуции обоих
сервисов.
