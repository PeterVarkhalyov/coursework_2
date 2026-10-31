"""Сервис, объединяющий данные Nominatim и OpenSky."""

from src.api import NominatimAPI, OpenSkyAPI
from src.models import CountryAirspace


class AirspaceCollector:
    """Собирает данные о воздушных судах для выбранных стран.

    Attributes:
        nominatim: клиент для получения координат и границ стран.
        opensky: клиент для получения информации о воздушных судах.

    Methods:
        collect(): собирает данные о воздушных судах для списка стран.
    """

    def __init__(self, nominatim: NominatimAPI, opensky: OpenSkyAPI) -> None:
        self.nominatim = nominatim
        self.opensky = opensky

    def collect(self, countries: list[str], airborne_only: bool = True) -> list[CountryAirspace]:
        country_names = [name.strip() for name in countries if name.strip()]
        if not country_names:
            raise ValueError("Нужно указать хотя бы одну страну")

        result: list[CountryAirspace] = []
        for country_name in country_names:
            country = self.nominatim.get_data(country_name)
            aircraft = self.opensky.get_data(country.bounding_box, airborne_only)
            result.append(CountryAirspace(country=country, aircraft=aircraft))
        return result
