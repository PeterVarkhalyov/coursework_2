"""Tests for the service that coordinates both APIs."""

from unittest.mock import Mock

import pytest

import src.service as service_module
from src.api import APIError
from src.models import AircraftState, BoundingBox, CountryCoordinates
from src.service import AirspaceCollector


def test_collector_returns_failure_for_empty_country_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.time, "time", Mock(return_value=1_766_142_246))
    collector = AirspaceCollector(Mock(), Mock())

    result = collector.collect(["", "   "])

    assert result == {
        "attribution": AirspaceCollector.ATTRIBUTION,
        "result": False,
        "msg": {"code": 1000, "error": "Нужно указать хотя бы одну страну"},
        "count": 0,
        "time": 1_766_142_246,
        "countries": [],
    }


def test_collector_returns_failure_for_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.time, "time", Mock(return_value=1_766_142_246))
    nominatim = Mock()
    nominatim.get_data.side_effect = APIError("Сообщение об ошибке")
    collector = AirspaceCollector(nominatim, Mock())

    result = collector.collect(["Россия"])

    assert result["result"] is False
    assert result["msg"] == {"code": 1000, "error": "Сообщение об ошибке"}
    assert result["count"] == 0
    assert result["countries"] == []


def test_collector_returns_success_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module.time, "time", Mock(return_value=1_766_142_246))
    country = CountryCoordinates("Россия", "RU", 64.6863136, 97.7453061, BoundingBox(10, 20, 30, 40))
    aircraft = AircraftState(
        icao24="abc123",
        callsign="TEST1",
        origin_country="Russian Federation",
        time_position=1_793_450_000,
        last_contact=1_793_450_005,
        longitude=37.6176,
        latitude=55.7558,
        baro_altitude=10_000.0,
        on_ground=False,
        velocity=230.0,
        true_track=90.0,
        vertical_rate=1.5,
        sensors=[1, 2],
        geo_altitude=10_100.0,
        squawk="7000",
        spi=False,
        position_source=0,
    )
    nominatim = Mock()
    nominatim.get_data.return_value = country
    opensky = Mock()
    opensky.get_data.return_value = (1_766_142_240, [aircraft])
    collector = AirspaceCollector(nominatim, opensky)

    result = collector.collect([" Россия ", ""], airborne_only=False)

    assert result == {
        "attribution": AirspaceCollector.ATTRIBUTION,
        "result": True,
        "msg": {"code": 0, "error": None},
        "count": 1,
        "time": 1_766_142_246,
        "countries": [
            {
                "country": {
                    "name": "Россия",
                    "country_code": "RU",
                    "latitude": 64.6863136,
                    "longitude": 97.7453061,
                    "bounding_box": {"south": 10, "north": 20, "west": 30, "east": 40},
                },
                "data": {
                    "count": 1,
                    "time": 1_766_142_240,
                    "aircraft": [
                        {
                            "icao24": "abc123",
                            "callsign": "TEST1",
                            "origin_country": "Russian Federation",
                            "time_position": 1_793_450_000,
                            "last_contact": 1_793_450_005,
                            "longitude": 37.6176,
                            "latitude": 55.7558,
                            "baro_altitude": 10_000.0,
                            "on_ground": False,
                            "velocity": 230.0,
                            "true_track": 90.0,
                            "vertical_rate": 1.5,
                            "sensors": [1, 2],
                            "geo_altitude": 10_100.0,
                            "squawk": "7000",
                            "spi": False,
                            "position_source": 0,
                        }
                    ],
                },
            }
        ],
    }
    nominatim.get_data.assert_called_once_with("Россия")
    opensky.get_data.assert_called_once_with(country.bounding_box, False)
