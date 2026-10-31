"""Tests for the project data models."""

from dataclasses import replace

import pytest

from src.models import AircraftState, BoundingBox

BASE_AIRCRAFT = AircraftState(
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


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((-91, 10, 20, 30), "широты"),
        ((20, 10, 20, 30), "широты"),
        ((10, 91, 20, 30), "широты"),
        ((10, 20, -181, 30), "долготы"),
        ((10, 20, 40, 30), "долготы"),
        ((10, 20, 30, 181), "долготы"),
    ],
)
def test_bounding_box_rejects_invalid_values(values: tuple[int, int, int, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        BoundingBox(*values)


def test_bounding_box_helpers() -> None:
    bounding_box = BoundingBox(south=10, north=20, west=30, east=40)

    assert bounding_box.contains(10, 30)
    assert bounding_box.contains(15, 35)
    assert not bounding_box.contains(9, 35)
    assert not bounding_box.contains(21, 35)
    assert not bounding_box.contains(15, 29)
    assert not bounding_box.contains(15, 41)
    assert bounding_box.to_query_params() == {
        "lamin": "10",
        "lamax": "20",
        "lomin": "30",
        "lomax": "40",
    }


def test_aircraft_normalizes_text_attributes() -> None:
    aircraft = replace(
        BASE_AIRCRAFT,
        icao24=" ABC123 ",
        callsign=" TEST2 ",
        origin_country=" Testland ",
        squawk=" 7700 ",
    )

    assert aircraft.icao24 == "abc123"
    assert aircraft.callsign == "TEST2"
    assert aircraft.origin_country == "Testland"
    assert aircraft.squawk == "7700"

    aircraft = replace(BASE_AIRCRAFT, callsign="   ", squawk=None, sensors=None)
    assert aircraft.callsign is None
    assert aircraft.squawk is None
    assert aircraft.sensors is None


@pytest.mark.parametrize("icao24", ["abc", "abc12z"])
def test_aircraft_rejects_invalid_icao24(icao24: str) -> None:
    with pytest.raises(ValueError, match="6 шестнадцатеричных"):
        replace(BASE_AIRCRAFT, icao24=icao24)


def test_aircraft_rejects_invalid_required_text() -> None:
    with pytest.raises(TypeError, match="icao24 должен иметь тип str"):
        replace(BASE_AIRCRAFT, icao24=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="origin_country не может быть пустым"):
        replace(BASE_AIRCRAFT, origin_country="   ")


def test_aircraft_rejects_invalid_optional_text() -> None:
    with pytest.raises(TypeError, match="callsign должен иметь тип str или None"):
        replace(BASE_AIRCRAFT, callsign=123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("longitude", True),
        ("latitude", "bad"),
        ("time_position", True),
        ("last_contact", 1.5),
    ],
)
def test_aircraft_rejects_invalid_numeric_types(attribute: str, value: object) -> None:
    with pytest.raises(TypeError):
        replace(BASE_AIRCRAFT, **{attribute: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("longitude", -181, "longitude"),
        ("longitude", 181, "longitude"),
        ("latitude", -91, "latitude"),
        ("latitude", 91, "latitude"),
        ("velocity", -1, "velocity"),
        ("true_track", -1, "true_track"),
        ("true_track", 361, "true_track"),
        ("position_source", -1, "position_source"),
    ],
)
def test_aircraft_rejects_values_outside_ranges(attribute: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(BASE_AIRCRAFT, **{attribute: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("on_ground", 1),
        ("spi", 0),
        ("sensors", "bad"),
        ("sensors", [True]),
        ("sensors", ["1"]),
    ],
)
def test_aircraft_rejects_invalid_flags_and_sensors(attribute: str, value: object) -> None:
    with pytest.raises(TypeError):
        replace(BASE_AIRCRAFT, **{attribute: value})  # type: ignore[arg-type]


def test_aircraft_altitude_prefers_geometric_and_falls_back_to_barometric() -> None:
    assert BASE_AIRCRAFT.altitude == 10_000.0
    assert replace(BASE_AIRCRAFT, geo_altitude=None).altitude == 9_900.0
    assert replace(BASE_AIRCRAFT, geo_altitude=None, baro_altitude=None).altitude is None


def test_aircraft_speed_comparison() -> None:
    faster = replace(BASE_AIRCRAFT, icao24="def456", velocity=250.0)
    same_speed = replace(BASE_AIRCRAFT, icao24="123abc")

    assert BASE_AIRCRAFT.compare_speed(faster) == -1
    assert faster.compare_speed(BASE_AIRCRAFT) == 1
    assert BASE_AIRCRAFT.compare_speed(same_speed) == 0
    assert faster.is_faster_than(BASE_AIRCRAFT)
    assert not BASE_AIRCRAFT.is_faster_than(faster)


def test_aircraft_altitude_comparison() -> None:
    higher = replace(BASE_AIRCRAFT, icao24="def456", geo_altitude=11_000.0)
    same_altitude = replace(BASE_AIRCRAFT, icao24="123abc")
    barometric = replace(BASE_AIRCRAFT, icao24="456def", geo_altitude=None, baro_altitude=9_000.0)

    assert BASE_AIRCRAFT.compare_altitude(higher) == -1
    assert higher.compare_altitude(BASE_AIRCRAFT) == 1
    assert BASE_AIRCRAFT.compare_altitude(same_altitude) == 0
    assert BASE_AIRCRAFT.compare_altitude(barometric) == 1
    assert higher.is_higher_than(BASE_AIRCRAFT)
    assert not BASE_AIRCRAFT.is_higher_than(higher)


def test_aircraft_comparison_requires_values() -> None:
    without_speed = replace(BASE_AIRCRAFT, velocity=None)
    without_altitude = replace(BASE_AIRCRAFT, geo_altitude=None, baro_altitude=None)

    with pytest.raises(ValueError, match="без данных о скорости"):
        without_speed.compare_speed(BASE_AIRCRAFT)
    with pytest.raises(ValueError, match="без данных о скорости"):
        BASE_AIRCRAFT.compare_speed(without_speed)
    with pytest.raises(ValueError, match="без данных о высоте"):
        without_altitude.compare_altitude(BASE_AIRCRAFT)
    with pytest.raises(ValueError, match="без данных о высоте"):
        BASE_AIRCRAFT.compare_altitude(without_altitude)


def test_aircraft_comparison_rejects_another_type() -> None:
    with pytest.raises(TypeError, match="только объекты AircraftState"):
        BASE_AIRCRAFT.compare_speed(object())
