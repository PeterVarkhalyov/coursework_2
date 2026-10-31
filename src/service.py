"""Сервис, объединяющий данные Nominatim и OpenSky."""

import time
from dataclasses import asdict
from typing import Any

from src.api import APIError, NominatimAPI, OpenSkyAPI


class AirspaceCollector:
    """Собирает данные о воздушных судах для выбранных стран.

    Attributes:
        nominatim: клиент для получения координат и границ стран.
        opensky: клиент для получения информации о воздушных судах.

    Methods:
        collect(): возвращает общий результат сбора в формате словаря.
    """

    ATTRIBUTION = [
        "Geocoding © OpenStreetMap contributors, ODbL 1.0",
        "Aircraft data © The OpenSky Network",
    ]
    SUCCESS_CODE = 0
    ERROR_CODE = 1000

    def __init__(self, nominatim: NominatimAPI, opensky: OpenSkyAPI) -> None:
        self.nominatim = nominatim
        self.opensky = opensky

    def collect(self, countries: list[str], airborne_only: bool = True) -> dict[str, Any]:
        """Собрать данные и вернуть ответ об успехе или ошибке."""

        timestamp = int(time.time())
        country_names = [name.strip() for name in countries if name.strip()]
        try:
            if not country_names:
                raise ValueError("Нужно указать хотя бы одну страну")

            countries_data: list[dict[str, Any]] = []
            for country_name in country_names:
                country = self.nominatim.get_data(country_name)
                server_time, aircraft = self.opensky.get_data(country.bounding_box, airborne_only)
                countries_data.append(
                    {
                        "country": asdict(country),
                        "data": {
                            "count": len(aircraft),
                            "time": server_time,
                            "aircraft": [asdict(item) for item in aircraft],
                        },
                    }
                )

            return {
                "attribution": self.ATTRIBUTION.copy(),
                "result": True,
                "msg": {"code": self.SUCCESS_CODE, "error": None},
                "count": len(countries_data),
                "time": timestamp,
                "countries": countries_data,
            }
        except (APIError, ValueError) as error:
            return {
                "attribution": self.ATTRIBUTION.copy(),
                "result": False,
                "msg": {"code": self.ERROR_CODE, "error": str(error)},
                "count": 0,
                "time": timestamp,
                "countries": [],
            }
