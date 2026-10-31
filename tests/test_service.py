"""Tests for the service that coordinates both APIs."""

from unittest.mock import Mock

import pytest

from src.models import BoundingBox, CountryCoordinates
from src.service import AirspaceCollector


def test_collector_rejects_empty_country_list() -> None:
    collector = AirspaceCollector(Mock(), Mock())

    with pytest.raises(ValueError, match="хотя бы одну страну"):
        collector.collect(["", "   "])


def test_collector_combines_country_and_aircraft() -> None:
    country = CountryCoordinates("Testland", "TL", 15, 35, BoundingBox(10, 20, 30, 40))
    nominatim = Mock()
    nominatim.get_data.return_value = country
    opensky = Mock()
    opensky.get_data.return_value = []
    collector = AirspaceCollector(nominatim, opensky)

    result = collector.collect([" Testland ", ""], airborne_only=False)

    assert len(result) == 1
    assert result[0].country is country
    assert result[0].aircraft == []
    nominatim.get_data.assert_called_once_with("Testland")
    opensky.get_data.assert_called_once_with(country.bounding_box, False)
