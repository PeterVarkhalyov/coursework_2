"""Integration tests joining the collector, console, and JSON storage."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.api import NominatimAPI, OpenSkyAPI
from src.main import user_interaction
from src.models import AircraftState, BoundingBox, CountryCoordinates
from src.service import AirspaceCollector
from src.storage import JSONAircraftStorage


def test_console_collects_and_saves_aircraft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    country = CountryCoordinates("Россия", "RU", 64.0, 97.0, BoundingBox(10, 20, 30, 40))
    aircraft = AircraftState(
        icao24="abc123",
        callsign="TEST1",
        origin_country="Testland",
        time_position=100,
        last_contact=101,
        longitude=35.0,
        latitude=15.0,
        baro_altitude=9_900.0,
        on_ground=False,
        velocity=200.0,
        true_track=90.0,
        vertical_rate=1.5,
        sensors=[1, 2],
        geo_altitude=10_000.0,
        squawk="7000",
        spi=False,
        position_source=0,
    )
    nominatim = Mock(spec=NominatimAPI)
    nominatim.get_data.return_value = country
    opensky = Mock(spec=OpenSkyAPI)
    opensky.get_data.return_value = (123, [aircraft])
    collector = AirspaceCollector(nominatim, opensky)
    file_path = tmp_path / "aircraft.json"
    storage = JSONAircraftStorage(file_path)
    answers = iter(["Россия", "4", "1", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    user_interaction(collector, storage)

    assert storage.get_aircraft() == [aircraft]
    document = json.loads(file_path.read_text(encoding="utf-8"))
    assert document["time"] == 123
    assert document["country"]["name"] == "Россия"
    assert document["country"]["country_code"] == "RU"
    assert document["country"]["count_aircraft"] == 1
    assert document["country"]["aircraft"] == [aircraft.to_dict()]
    nominatim.get_data.assert_called_once_with("Россия")
    opensky.get_data.assert_called_once_with(country.bounding_box, True)
