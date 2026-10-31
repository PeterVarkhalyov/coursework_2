"""Модели данных."""

from dataclasses import dataclass


@dataclass
class BoundingBox:
    """Объявление прямоугольных границ страны.
    Attributes:
      south, north: координаты широты
      west, east: координаты долготы

    Methods:
      __post_init__(): проверка корректности координат
      contains(): проверка попадпния точки в границы координат
      to_query_params(): подготовка границ для запроса к OpenSky
    """

    south: float
    north: float
    west: float
    east: float

    def __post_init__(self) -> None:
        if not -90 <= self.south <= self.north <= 90:
            raise ValueError("Некорректные границы широты")
        if not -180 <= self.west <= self.east <= 180:
            raise ValueError("Некорректные границы долготы")

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.south <= latitude <= self.north and self.west <= longitude <= self.east

    def to_query_params(self) -> dict[str, str]:
        return {
            "lamin": str(self.south),
            "lamax": str(self.north),
            "lomin": str(self.west),
            "lomax": str(self.east),
        }


@dataclass
class CountryCoordinates:
    """Название, координаты и границы страны.
    Attributes:
        name: наименование страны, возвращённое Nominatim
        country_code: двухбуквенный код страны по стандарту ISO 3166-1
        latitude: широта центральной точки страны в градусах
        longitude: долгота центральной точки страны в градусах
        bounding_box: объект класса BoundingBox, содержащий прямоугольные границы страны
    """

    name: str
    country_code: str | None
    latitude: float
    longitude: float
    bounding_box: BoundingBox


@dataclass
class AircraftState:
    """Основная информация об одном воздушном судне, полученной от OpenSky.
    Attributes:
        icao24: уникальный 24-битный адрес транспондера воздушного судна в шестнадцатеричном формате
        callsign: позывной воздушного судна
        origin_country: страна, определённая OpenSky по ICAO24-адресу транспондера
        time_position: время последнего обновления позиции в формате UNIX
        last_contact: время последнего контакта в формате UNIX
        longitude: текущая географическая долгота воздушного судна
        latitude: текущая географическая широта воздушного судна
        baro_altitude: барометрическая высота воздушного судна в метрах
        on_ground: находится ли самолёт на земле
        velocity: горизонтальная скорость (м/с)
        true_track: курс (градусы)
        vertical_rate: вертикальная скорость (м/с)
        sensors: ID сенсоров
        geo_altitude: геометрическая высота (м)
        squawk: код ответчика (транспондера)
        spi: специальный сигнал
        position_source: источник позиции

    """

    icao24: str
    callsign: str | None
    origin_country: str
    time_position: int | None
    last_contact: int | None
    longitude: float | None
    latitude: float | None
    baro_altitude: float | None
    on_ground: bool
    velocity: float | None
    true_track: float | None
    vertical_rate: float | None
    sensors: list[int] | None
    geo_altitude: float | None
    squawk: str | None
    spi: bool
    position_source: int | None


@dataclass
class CountryAirspace:
    """Страна и найденные в её прямоугольных границах воздушные судна.
    Attributes:
        country: объект класса CountryCoordinates, содержащий информацию о выбранной стране
        aircraft: Список объектов AircraftState, каждый объект содержит сведения об одном воздушном судне
    """

    country: CountryCoordinates
    aircraft: list[AircraftState]
