"""Сервис, объединяющий данные Nominatim и OpenSky."""

import time
from dataclasses import asdict
from typing import Any

from src.api import APIError
from src.interfaces import AircraftProvider, CountryProvider
from src.models import CountryAirspace


class AirspaceCollector:
    """Собирает данные о воздушных судах для выбранных стран.

    Attributes:
        country_provider: поставщик координат и границ стран.
        aircraft_provider: поставщик информации о воздушных судах.

    Methods:
        collect(): возвращает общий результат сбора в формате словаря.
    """

    ATTRIBUTION = [
        "Geocoding © OpenStreetMap contributors, ODbL 1.0",
        "Aircraft data © The OpenSky Network",
    ]
    SUCCESS_CODE = 0
    ERROR_CODE = 1000

    def __init__(self, country_provider: CountryProvider, aircraft_provider: AircraftProvider) -> None:
        self.country_provider = country_provider
        self.aircraft_provider = aircraft_provider

    def collect_country(self, country_name: str, airborne_only: bool = True) -> tuple[int, CountryAirspace]:
        """Получить время OpenSky и типизированные данные для одной страны."""

        country_name = country_name.strip()
        if not country_name:
            raise ValueError("Название страны не может быть пустым")

        country = self.country_provider.get_data(country_name)
        server_time, aircraft = self.aircraft_provider.get_data(country.bounding_box, airborne_only)
        return server_time, CountryAirspace(country=country, aircraft=aircraft)

    def collect(self, countries: list[str], airborne_only: bool = True) -> dict[str, Any]:
        """Собрать данные и вернуть ответ об успехе или ошибке."""

        timestamp = int(time.time())
        country_names = [name.strip() for name in countries if name.strip()]
        try:
            if not country_names:
                raise ValueError("Нужно указать хотя бы одну страну")

            countries_data: list[dict[str, Any]] = []
            for country_name in country_names:
                server_time, airspace = self.collect_country(country_name, airborne_only)
                countries_data.append(
                    {
                        "country": asdict(airspace.country),
                        "data": {
                            "count": len(airspace.aircraft),
                            "time": server_time,
                            "aircraft": [item.to_dict() for item in airspace.aircraft],
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
