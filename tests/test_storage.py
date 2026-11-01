"""Tests for aircraft file storage connectors."""

import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import Mock

import pytest

from src.models import AircraftState
from src.storage import (
    AbstractAircraftStorage,
    CSVAircraftStorage,
    JSONAircraftStorage,
    SQLAircraftStorage,
    StorageError,
    TXTAircraftStorage,
    XLSXAircraftStorage,
)


@pytest.fixture
def aircraft() -> AircraftState:
    """Return a valid aircraft used by storage tests."""

    return AircraftState(
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


def test_abstract_storage_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        AbstractAircraftStorage()  # type: ignore[abstract]


@pytest.mark.parametrize(
    "storage_class",
    [CSVAircraftStorage, TXTAircraftStorage, XLSXAircraftStorage, SQLAircraftStorage],
)
def test_optional_storage_placeholders_remain_abstract(
    storage_class: type[AbstractAircraftStorage],
) -> None:
    with pytest.raises(TypeError):
        storage_class()  # type: ignore[abstract]


def test_json_storage_uses_default_path() -> None:
    storage = JSONAircraftStorage()

    assert storage.file_path == Path("data/aircraft.json")


def test_missing_file_is_an_empty_storage(tmp_path: Path) -> None:
    storage = JSONAircraftStorage(tmp_path / "missing.json")

    assert storage.get_aircraft() == []


def test_add_read_and_filter_aircraft(tmp_path: Path, aircraft: AircraftState) -> None:
    file_path = tmp_path / "nested" / "aircraft.json"
    storage = JSONAircraftStorage(str(file_path))
    second_aircraft = replace(
        aircraft,
        icao24="def456",
        callsign="SECOND",
        origin_country="Россия",
        velocity=250.0,
        on_ground=True,
    )

    storage.add_aircraft(aircraft)
    storage.add_aircraft(second_aircraft)

    assert storage.get_aircraft() == [aircraft, second_aircraft]
    assert storage.get_aircraft({}) == [aircraft, second_aircraft]
    assert storage.get_aircraft(MappingProxyType({"origin_country": "Россия", "on_ground": True})) == [second_aircraft]
    assert storage.get_aircraft({"callsign": "UNKNOWN"}) == []
    assert "Россия" in file_path.read_text(encoding="utf-8")
    assert len(json.loads(file_path.read_text(encoding="utf-8"))) == 2


def test_add_rejects_an_object_of_another_type(tmp_path: Path) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")

    with pytest.raises(TypeError, match="AircraftState"):
        storage.add_aircraft({"icao24": "abc123"})  # type: ignore[arg-type]


def test_delete_aircraft_rewrites_file(tmp_path: Path, aircraft: AircraftState) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    second_aircraft = replace(aircraft, icao24="def456", callsign="SECOND")
    storage.add_aircraft(aircraft)
    storage.add_aircraft(second_aircraft)

    deleted_count = storage.delete_aircraft({"icao24": "abc123"})

    assert deleted_count == 1
    assert storage.get_aircraft() == [second_aircraft]


def test_delete_without_matches_does_not_rewrite_file(
    tmp_path: Path,
    aircraft: AircraftState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    storage.add_aircraft(aircraft)
    write_records = Mock(side_effect=AssertionError("File must not be rewritten"))
    monkeypatch.setattr(storage, "_write_records", write_records)

    assert storage.delete_aircraft({"icao24": "def456"}) == 0
    write_records.assert_not_called()


def test_delete_rejects_empty_criteria(tmp_path: Path) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")

    with pytest.raises(ValueError, match="хотя бы один критерий"):
        storage.delete_aircraft({})


def test_criteria_must_be_a_mapping(tmp_path: Path) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")

    with pytest.raises(TypeError, match="criteria"):
        storage.get_aircraft([("icao24", "abc123")])  # type: ignore[arg-type]


def test_criteria_reject_unknown_fields(tmp_path: Path) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")

    with pytest.raises(ValueError, match="bad_field, unknown"):
        storage.get_aircraft({"unknown": 1, "bad_field": 2})


@pytest.mark.parametrize("content", ["{}", "[1]"])
def test_read_rejects_invalid_json_structure(tmp_path: Path, content: str) -> None:
    file_path = tmp_path / "aircraft.json"
    file_path.write_text(content, encoding="utf-8")
    storage = JSONAircraftStorage(file_path)

    with pytest.raises(StorageError, match="список объектов"):
        storage.get_aircraft()


def test_read_rejects_malformed_json(tmp_path: Path) -> None:
    file_path = tmp_path / "aircraft.json"
    file_path.write_text("not json", encoding="utf-8")
    storage = JSONAircraftStorage(file_path)

    with pytest.raises(StorageError, match="Не удалось прочитать"):
        storage.get_aircraft()


def test_read_converts_os_error_to_storage_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "aircraft.json"
    file_path.write_text("[]", encoding="utf-8")
    storage = JSONAircraftStorage(file_path)

    def fail_read(*args: Any, **kwargs: Any) -> str:
        raise OSError("Access denied")

    monkeypatch.setattr(Path, "read_text", fail_read)

    with pytest.raises(StorageError, match="Не удалось прочитать"):
        storage.get_aircraft()


@pytest.mark.parametrize(
    "record",
    [
        {"icao24": "abc123"},
        {
            "icao24": "invalid",
            "callsign": None,
            "origin_country": "Testland",
            "time_position": None,
            "last_contact": None,
            "longitude": None,
            "latitude": None,
            "baro_altitude": None,
            "on_ground": False,
            "velocity": None,
            "true_track": None,
            "vertical_rate": None,
            "sensors": None,
            "geo_altitude": None,
            "squawk": None,
            "spi": False,
            "position_source": None,
        },
    ],
)
def test_read_rejects_invalid_aircraft_record(tmp_path: Path, record: dict[str, Any]) -> None:
    file_path = tmp_path / "aircraft.json"
    file_path.write_text(json.dumps([record]), encoding="utf-8")
    storage = JSONAircraftStorage(file_path)

    with pytest.raises(StorageError, match="некорректную запись"):
        storage.get_aircraft()


def test_write_converts_os_error_to_storage_error(
    tmp_path: Path,
    aircraft: AircraftState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")

    def fail_write(*args: Any, **kwargs: Any) -> int:
        raise OSError("Access denied")

    monkeypatch.setattr(Path, "write_text", fail_write)

    with pytest.raises(StorageError, match="Не удалось записать"):
        storage.add_aircraft(aircraft)


def test_write_converts_serialization_error_to_storage_error(tmp_path: Path) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")

    with pytest.raises(StorageError, match="Не удалось записать"):
        storage._write_records([{"not_serializable": object()}])
