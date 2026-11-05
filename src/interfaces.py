"""Структурные контракты между слоями приложения."""

from typing import Protocol

from src.models import AircraftState, BoundingBox, CountryAirspace, CountryCoordinates


class CountryProvider(Protocol):
    """Контракт поставщика координат и границ страны."""

    def get_data(self, country_name: str) -> CountryCoordinates:
        """Получить координаты и границы страны по её названию."""


class AircraftProvider(Protocol):
    """Контракт поставщика состояний воздушных судов."""

    def get_data(
        self,
        bounding_box: BoundingBox,
        airborne_only: bool = True,
    ) -> tuple[int, list[AircraftState]]:
        """Получить время сервера и воздушные суда в заданных границах."""


class AirspaceService(Protocol):
    """Контракт сервиса сбора типизированных данных по одной стране."""

    def collect_country(
        self,
        country_name: str,
        airborne_only: bool = True,
    ) -> tuple[int, CountryAirspace]:
        """Получить время сервера и данные воздушного пространства страны."""
