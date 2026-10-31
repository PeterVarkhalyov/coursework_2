"""Классы для работы с Nominatim и OpenSky."""

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.models import AircraftState, BoundingBox, CountryCoordinates


class APIError(Exception):
    """Ошибка подключения к API или обработки его ответа."""


class AbstractAPIClient(ABC):
    """Общий абстрактный родительский класс для клиентов Nominatim и OpenSky.

    Attributes:
        base_url: содержит основной адрес API
        timeout: определяет максимальное время ожидания ответа от API в секундах

    Methods:
        __init__(): конструктор вызывается при создании API-клиента
        connect(): абстрактный метод означает, что каждый дочерний класс обязан
            предоставить собственную реализацию этого метода
        _request_json(): основной HTTP-метод класса, выполняет GET-запрос и возвращает разобранный JSON

    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @abstractmethod
    def connect(self) -> bool:
        """Проверить или подготовить подключение к API."""

    def _request_json(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:

        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"

        request = Request(url, headers=headers or {})
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise APIError(f"API вернуло HTTP {error.code}") from error
        except URLError as error:
            raise APIError(f"Не удалось подключиться к API: {error.reason}") from error
        except (TimeoutError, json.JSONDecodeError) as error:
            raise APIError("API не ответило или вернуло некорректные данные") from error


class NominatimAPI(AbstractAPIClient):
    """Класс получения географических координат и прямоугольных границ страны через сервис Nominatim

    Attributes:
        base_url: основной адрес Nominatim API, атрибут создаётся в родительском классе
        timeout: максимальное время ожидания ответа от Nominatim в секундах, атрибут создаётся родительским классом
        user_agent: название приложения, которое передаётся Nominatim в HTTP-заголовке
        _last_request_time: хранит время выполнения предыдущего запроса к Nominatim
        _cache: словарь, в котором сохраняются уже полученные страны

    Methods:
          __init__(): конструктор создаёт и настраивает клиент Nominatim
          connect(): проверяет доступность Nominatim
          get_data(): главный публичный метод класса, получает название страны и возвращает объект CountryCoordinates
          _request(): внутренний метод Nominatim, который: ограничивает частоту запросов,
            добавляет User-Agent, вызывает общий _request_json()
    """

    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org",
        user_agent: str = "coursework-2-airspace/1.0",
        timeout: float = 30.0,
    ) -> None:
        super().__init__(base_url, timeout)
        self.user_agent = user_agent
        self._last_request_time = 0.0
        self._cache: dict[str, CountryCoordinates] = {}

    def connect(self) -> bool:
        response = self._request("status", {"format": "json"})
        return isinstance(response, dict) and response.get("status") == 0

    def get_data(self, country_name: str) -> CountryCoordinates:
        country_name = country_name.strip()
        if not country_name:
            raise ValueError("Название страны не может быть пустым")

        cache_key = country_name.casefold()
        if cache_key in self._cache:
            return self._cache[cache_key]

        response = self._request(
            "search",
            {
                "country": country_name,
                "format": "jsonv2",
                "limit": "1",
                "addressdetails": "1",
                "featureType": "country",
                "accept-language": "ru,en",
            },
        )
        if not isinstance(response, list) or not response or not isinstance(response[0], dict):
            raise APIError(f"Страна не найдена: {country_name}")

        item = response[0]
        bounding_box = item.get("boundingbox")
        if not isinstance(bounding_box, list) or len(bounding_box) != 4:
            raise APIError("Nominatim не вернул границы страны")

        try:
            address = item.get("address", {})
            country_code = address.get("country_code") if isinstance(address, dict) else None
            country = CountryCoordinates(
                name=str(item.get("display_name", country_name)),
                country_code=country_code.upper() if isinstance(country_code, str) else None,
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                bounding_box=BoundingBox(
                    south=float(bounding_box[0]),
                    north=float(bounding_box[1]),
                    west=float(bounding_box[2]),
                    east=float(bounding_box[3]),
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise APIError("Nominatim вернул некорректные координаты") from error

        self._cache[cache_key] = country
        return country

    def _request(self, path: str, params: dict[str, str]) -> Any:
        passed = time.monotonic() - self._last_request_time
        if passed < 1.0:
            time.sleep(1.0 - passed)
        try:
            return self._request_json(path, params, {"User-Agent": self.user_agent})
        finally:
            self._last_request_time = time.monotonic()


class OpenSkyAPI(AbstractAPIClient):
    """Класс OpenSkyAPI предназначен для получения информации о воздушных судах,
        находящихся в заданных географических границах

    Attributes: не создаёт собственных атрибутов, использует атрибуты, унаследованные от AbstractAPIClient

    Methods:
        __init__(): конструктор вызывает родительский класс
        connect(): метод реализует обязательный абстрактный метод родительского класса
        get_data(): главный публичный метод класса - получает географические границы и
            возвращает список воздушных судов.
        _parse_aircraft(): внутренний статический метод, преобразующий массив OpenSky в объект AircraftState
        _to_float(): безопасно преобразует значение в float
        _to_int(): безопасно преобразует значение в int
        _to_int_list(): безопасно преобразует значение в список целых чисел
    """

    def __init__(self, base_url: str = "https://opensky-network.org/api", timeout: float = 30.0) -> None:
        super().__init__(base_url, timeout)

    def connect(self) -> bool:
        # OpenSky разрешает анонимные запросы, поэтому отдельная авторизация не нужна.
        return True

    def get_data(self, bounding_box: BoundingBox, airborne_only: bool = True) -> tuple[int, list[AircraftState]]:
        params: dict[str, str | int] = {"extended": 1}
        params.update(bounding_box.to_query_params())
        response = self._request_json("states/all", params)
        if not isinstance(response, dict):
            raise APIError("OpenSky вернул неожиданный ответ")

        server_time = response.get("time")
        if not isinstance(server_time, int) or isinstance(server_time, bool):
            raise APIError("OpenSky не вернул корректное время сервера")

        states = response.get("states") or []
        if not isinstance(states, list):
            raise APIError("OpenSky вернул некорректный список самолётов")

        aircraft: list[AircraftState] = []
        for item in states:
            state = self._parse_aircraft(item)
            if state is None:
                continue
            if airborne_only and state.on_ground:
                continue
            if state.latitude is None or state.longitude is None:
                continue
            if bounding_box.contains(state.latitude, state.longitude):
                aircraft.append(state)
        return server_time, aircraft

    @staticmethod
    def _parse_aircraft(item: Any) -> AircraftState | None:
        if not isinstance(item, list) or len(item) < 17:
            return None
        if not isinstance(item[0], str) or not isinstance(item[2], str):
            return None
        if item[5] is None or item[6] is None or not isinstance(item[8], bool):
            return None

        try:
            callsign = item[1].strip() if isinstance(item[1], str) else None
            return AircraftState(
                icao24=item[0],
                callsign=callsign or None,
                origin_country=item[2],
                time_position=OpenSkyAPI._to_int(item[3]),
                last_contact=OpenSkyAPI._to_int(item[4]),
                longitude=OpenSkyAPI._to_float(item[5]),
                latitude=OpenSkyAPI._to_float(item[6]),
                baro_altitude=OpenSkyAPI._to_float(item[7]),
                on_ground=item[8],
                velocity=OpenSkyAPI._to_float(item[9]),
                true_track=OpenSkyAPI._to_float(item[10]),
                vertical_rate=OpenSkyAPI._to_float(item[11]),
                sensors=OpenSkyAPI._to_int_list(item[12]),
                geo_altitude=OpenSkyAPI._to_float(item[13]),
                squawk=item[14] if isinstance(item[14], str) else None,
                spi=item[15] if isinstance(item[15], bool) else False,
                position_source=OpenSkyAPI._to_int(item[16]),
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int_list(value: Any) -> list[int] | None:
        if not isinstance(value, list):
            return None
        try:
            return [int(item) for item in value if not isinstance(item, bool)]
        except (TypeError, ValueError):
            return None
