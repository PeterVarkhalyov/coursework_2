"""Tests for the console application without network access."""

import runpy
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import src.main as main_module
from src.api import APIError
from src.main import (
    _add_aircraft,
    _aircraft_menu,
    _altitude_for_sorting,
    _delete_aircraft_menu,
    _file_menu,
    _read_aircraft_coordinates,
    _read_aircraft_state,
    _read_console_value_or_escape,
    _read_float_in_range,
    _read_icao24_or_escape,
    _read_optional_aircraft_numbers,
    _read_optional_float_or_escape,
    _read_required_text_or_escape,
    _remove_existing_aircraft_file,
    _save_aircraft,
    _show_by_origin_country,
    get_aircraft_by_origin_country,
    get_top_aircraft_by_altitude,
    user_interaction,
)
from src.models import AircraftState, BoundingBox, CountryAirspace, CountryCoordinates
from src.service import AirspaceCollector
from src.storage import AbstractAircraftStorage, JSONAircraftStorage, StorageError


@pytest.fixture
def aircraft() -> AircraftState:
    """Return a valid aircraft used by console tests."""

    return AircraftState(
        icao24="abc123",
        callsign="TEST1",
        origin_country="United States",
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


@pytest.fixture
def airspace(aircraft: AircraftState) -> CountryAirspace:
    """Return a country with aircraft covering all display variants."""

    higher = replace(
        aircraft,
        icao24="def456",
        callsign="SECOND",
        origin_country="Germany",
        velocity=250.0,
        geo_altitude=12_000.0,
    )
    unknown = replace(
        aircraft,
        icao24="123def",
        callsign=None,
        origin_country="Canada",
        longitude=None,
        latitude=None,
        velocity=None,
        geo_altitude=None,
        baro_altitude=None,
    )
    country = CountryCoordinates("Россия", "RU", 64.0, 97.0, BoundingBox(10, 20, 30, 40))
    return CountryAirspace(country=country, aircraft=[aircraft, higher, unknown])


def set_inputs(monkeypatch: pytest.MonkeyPatch, values: list[str]) -> None:
    """Replace input() with values returned in order."""

    answers = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))


def test_top_aircraft_by_altitude(airspace: CountryAirspace) -> None:
    result = get_top_aircraft_by_altitude(airspace.aircraft, 2)

    assert [item.icao24 for item in result] == ["def456", "abc123"]
    assert [item.icao24 for item in get_top_aircraft_by_altitude(airspace.aircraft, 2, sort=False)] == [
        "abc123",
        "def456",
    ]
    assert _altitude_for_sorting(airspace.aircraft[-1]) == float("-inf")

    with pytest.raises(ValueError, match="положительным"):
        get_top_aircraft_by_altitude(airspace.aircraft, 0)


def test_filter_aircraft_by_origin_country(airspace: CountryAirspace) -> None:
    result = get_aircraft_by_origin_country(airspace.aircraft, "  gErMaNy ")

    assert [item.icao24 for item in result] == ["def456"]
    assert get_aircraft_by_origin_country(airspace.aircraft, "France") == []

    with pytest.raises(ValueError, match="не может быть пустой"):
        get_aircraft_by_origin_country(airspace.aircraft, "   ")


def test_user_interaction_retries_and_requests_another_country(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    collector = Mock(spec=AirspaceCollector)
    collector.collect_country.side_effect = [APIError("API недоступен"), (123, airspace)]
    storage = Mock(spec=AbstractAircraftStorage)
    set_inputs(monkeypatch, ["", "Ошибка", "Россия", "5", "0"])

    user_interaction(collector, storage)

    output = capsys.readouterr().out
    assert "Название страны не может быть пустым" in output
    assert "Не удалось получить данные: API недоступен" in output
    assert "Найдено воздушных судов: 3" in output
    assert collector.collect_country.call_args_list == [call("Ошибка"), call("Россия")]


def test_user_interaction_handles_all_main_menu_actions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
    tmp_path: Path,
) -> None:
    collector = Mock(spec=AirspaceCollector)
    collector.collect_country.return_value = (123, airspace)
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    set_inputs(
        monkeypatch,
        ["Россия", "unknown", "1", "not a number", "0", "2", "2", "germany", "3", "4", "1", "0"],
    )

    user_interaction(collector, storage)

    output = capsys.readouterr().out
    assert "Неизвестный пункт меню" in output
    assert output.count("Введите положительное целое число") == 2
    assert "Топ-2 воздушных судов" in output
    assert "Воздушные суда со страной регистрации germany" in output
    assert "без позывного" in output
    assert "высота: нет данных" in output
    assert "скорость: нет данных" in output
    assert "longitude: 35.0000" in output
    assert "latitude: нет данных" in output
    assert "Сохранено воздушных судов: 3" in output
    assert "Файл успешно сформирован: data/aircraft.json" in output
    assert storage.get_aircraft() == airspace.aircraft


def test_empty_aircraft_menu_actions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    set_inputs(monkeypatch, ["1", "2", "3", "4", "1", "0"])
    empty_airspace = CountryAirspace(
        country=CountryCoordinates("Россия", "RU", 64.0, 97.0, BoundingBox(10, 20, 30, 40)),
        aircraft=[],
    )

    assert _aircraft_menu(123, empty_airspace, storage) is False

    output = capsys.readouterr().out
    assert "Нет воздушных судов с известной высотой" in output
    assert "Список воздушных судов пуст" in output
    assert "Воздушные суда не найдены" in output
    assert "Нет воздушных судов для сохранения" in output
    assert not storage.file_path.exists()


def test_registration_filter_handles_empty_and_unknown_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    set_inputs(monkeypatch, [" ", "France"])

    _show_by_origin_country(airspace.aircraft)
    _show_by_origin_country(airspace.aircraft)

    output = capsys.readouterr().out
    assert "Страна регистрации не может быть пустой" in output
    assert "со страной регистрации France не найдены" in output


def test_save_aircraft_handles_storage_error(
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    storage = Mock(spec=AbstractAircraftStorage)
    storage.replace_airspace.side_effect = StorageError("доступ запрещён")

    _save_aircraft(123, airspace, storage)

    assert "Не удалось сохранить данные: доступ запрещён" in capsys.readouterr().out


def test_save_aircraft_does_not_overwrite_existing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    storage.replace_airspace(123, airspace)

    _save_aircraft(456, airspace, storage)

    assert "Файл уже сохранен" in capsys.readouterr().out
    assert storage.get_aircraft() == airspace.aircraft


def test_aircraft_menu_rejects_non_json_storage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    set_inputs(monkeypatch, ["4", "0"])

    assert _aircraft_menu(123, airspace, Mock(spec=AbstractAircraftStorage)) is False
    assert "доступна только для JSON-хранилища" in capsys.readouterr().out


def test_aircraft_menu_returns_from_file_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    airspace: CountryAirspace,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    set_inputs(monkeypatch, ["4", "4", "0"])

    assert _aircraft_menu(123, airspace, storage) is False


def test_file_menu_handles_missing_file_and_choices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    set_inputs(monkeypatch, ["unknown", "2", "3", "4"])

    assert _file_menu(123, airspace, storage) is True

    output = capsys.readouterr().out
    assert "Неизвестный пункт меню" in output
    assert output.count("Предварительно сохраните файл") == 2

    set_inputs(monkeypatch, ["0"])
    assert _file_menu(123, airspace, storage) is False


def test_file_menu_opens_delete_and_add_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    airspace: CountryAirspace,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    storage.replace_airspace(123, airspace)
    delete_menu = Mock()
    add_aircraft = Mock()
    monkeypatch.setattr(main_module, "_delete_aircraft_menu", delete_menu)
    monkeypatch.setattr(main_module, "_add_aircraft", add_aircraft)
    set_inputs(monkeypatch, ["2", "3", "4"])

    assert _file_menu(123, airspace, storage) is True
    delete_menu.assert_called_once_with(storage)
    add_aircraft.assert_called_once_with(airspace, storage)


def test_delete_aircraft_menu_handles_all_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    storage.replace_airspace(123, airspace)
    set_inputs(
        monkeypatch,
        [
            "unknown",
            "1",
            " ",
            "1",
            "United States",
            "3",
            "SECOND",
            "2",
            " 1 2 3 D E F ",
            "4",
        ],
    )

    _delete_aircraft_menu(storage)

    output = capsys.readouterr().out
    assert "Неизвестный пункт меню" in output
    assert "Значение фильтра не может быть пустым" in output
    assert "Удалено 1, сохранено 2" in output
    assert "Удалено 1, сохранено 1" in output
    assert "Удалено 1, сохранено 0" in output
    assert storage.get_aircraft() == []


def test_delete_aircraft_menu_handles_storage_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = Mock(spec=JSONAircraftStorage)
    storage.delete_aircraft.side_effect = StorageError("повреждённый файл")
    set_inputs(monkeypatch, ["1", "France", "4"])

    _delete_aircraft_menu(storage)

    assert "Не удалось удалить записи: повреждённый файл" in capsys.readouterr().out


def test_add_aircraft_saves_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
    aircraft: AircraftState,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    storage.replace_airspace(123, airspace)
    added_aircraft = replace(aircraft, icao24="fed321", callsign="ADDED")
    monkeypatch.setattr(main_module, "_read_aircraft_coordinates", Mock(return_value=(35.0, 15.0)))
    monkeypatch.setattr(main_module, "_read_aircraft_state", Mock(return_value=added_aircraft))

    _add_aircraft(airspace, storage)

    assert storage.get_aircraft()[-1] == added_aircraft
    assert "добавлено 1 записей" in capsys.readouterr().out


def test_add_aircraft_handles_cancellation_and_storage_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
    aircraft: AircraftState,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    coordinates = Mock(return_value=None)
    read_state = Mock(return_value=aircraft)
    monkeypatch.setattr(main_module, "_read_aircraft_coordinates", coordinates)
    monkeypatch.setattr(main_module, "_read_aircraft_state", read_state)

    _add_aircraft(airspace, storage)
    read_state.assert_not_called()

    coordinates.return_value = (35.0, 15.0)
    read_state.return_value = None
    _add_aircraft(airspace, storage)

    read_state.return_value = aircraft
    storage.add_aircraft = Mock(side_effect=StorageError("нет доступа"))  # type: ignore[method-assign]
    _add_aircraft(airspace, storage)
    assert "Не удалось добавить запись: нет доступа" in capsys.readouterr().out


def test_read_aircraft_state_handles_each_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    required_text = Mock(return_value=None)
    read_icao24 = Mock(return_value="abc123")
    read_numbers = Mock(return_value={})
    read_console = Mock(return_value="7000")
    monkeypatch.setattr(main_module, "_read_required_text_or_escape", required_text)
    monkeypatch.setattr(main_module, "_read_icao24_or_escape", read_icao24)
    monkeypatch.setattr(main_module, "_read_optional_aircraft_numbers", read_numbers)
    monkeypatch.setattr(main_module, "_read_console_value_or_escape", read_console)

    assert _read_aircraft_state(35.0, 15.0) is None

    required_text.return_value = "France"
    read_icao24.return_value = None
    assert _read_aircraft_state(35.0, 15.0) is None

    read_icao24.return_value = "abc123"
    required_text.side_effect = ["France", None]
    assert _read_aircraft_state(35.0, 15.0) is None

    required_text.side_effect = ["France", "CALL"]
    read_numbers.return_value = None
    assert _read_aircraft_state(35.0, 15.0) is None

    required_text.side_effect = ["France", "CALL"]
    read_numbers.return_value = {
        "baro_altitude": None,
        "geo_altitude": None,
        "velocity": None,
        "vertical_rate": None,
        "true_track": None,
    }
    read_console.return_value = None
    assert _read_aircraft_state(35.0, 15.0) is None


def test_read_aircraft_state_builds_valid_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required_text = Mock(side_effect=["France", "CALL"])
    monkeypatch.setattr(main_module, "_read_required_text_or_escape", required_text)
    monkeypatch.setattr(main_module, "_read_icao24_or_escape", Mock(return_value="abc123"))
    monkeypatch.setattr(
        main_module,
        "_read_optional_aircraft_numbers",
        Mock(
            return_value={
                "baro_altitude": 10_000.0,
                "geo_altitude": 10_100.0,
                "velocity": 200.0,
                "vertical_rate": 1.0,
                "true_track": 90.0,
            }
        ),
    )
    monkeypatch.setattr(main_module, "_read_console_value_or_escape", Mock(return_value=" "))
    monkeypatch.setattr(main_module.time, "time", Mock(return_value=456.9))

    result = _read_aircraft_state(35.0, 15.0)

    assert result is not None
    assert result.time_position == 456
    assert result.last_contact == 456
    assert result.squawk is None
    assert result.on_ground is False
    assert result.sensors is None


def test_read_aircraft_state_handles_model_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(main_module, "_read_required_text_or_escape", Mock(side_effect=["France", "CALL"]))
    monkeypatch.setattr(main_module, "_read_icao24_or_escape", Mock(return_value="invalid"))
    monkeypatch.setattr(
        main_module,
        "_read_optional_aircraft_numbers",
        Mock(
            return_value={
                "baro_altitude": None,
                "geo_altitude": None,
                "velocity": None,
                "vertical_rate": None,
                "true_track": None,
            }
        ),
    )
    monkeypatch.setattr(main_module, "_read_console_value_or_escape", Mock(return_value="7000"))

    assert _read_aircraft_state(35.0, 15.0) is None
    assert "Не удалось добавить запись" in capsys.readouterr().out


def test_read_optional_aircraft_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = Mock(side_effect=[(False, 1.0), (False, 2.0), (False, 3.0), (False, 4.0), (False, 5.0)])
    monkeypatch.setattr(main_module, "_read_optional_float_or_escape", reader)

    assert _read_optional_aircraft_numbers() == {
        "baro_altitude": 1.0,
        "geo_altitude": 2.0,
        "velocity": 3.0,
        "vertical_rate": 4.0,
        "true_track": 5.0,
    }

    reader.side_effect = [(True, None)]
    assert _read_optional_aircraft_numbers() is None


def test_read_aircraft_coordinates_retries_and_can_cancel(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    airspace: CountryAirspace,
) -> None:
    set_inputs(monkeypatch, ["0", "0", "unknown", "1", "35", "15"])

    assert _read_aircraft_coordinates(airspace) == (35.0, 15.0)
    assert "не соответствуют обрабатываемой стране" in capsys.readouterr().out

    set_inputs(monkeypatch, ["0", "0", "0"])
    assert _read_aircraft_coordinates(airspace) is None


def test_read_float_in_range_validates_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_inputs(monkeypatch, [" ", "text", "nan", "181", "180"])

    assert _read_float_in_range("value: ", -180, 180) == 180

    output = capsys.readouterr().out
    assert "не может быть пустым" in output
    assert "Введите число" in output
    assert "Введите конечное число" in output
    assert "в диапазоне" in output


def test_read_required_text_and_icao24(monkeypatch: pytest.MonkeyPatch) -> None:
    set_inputs(monkeypatch, [" ", " A B C "])
    assert _read_required_text_or_escape("value: ", remove_spaces=True) == "ABC"

    set_inputs(monkeypatch, ["short", "gggggg", " A B C 1 2 3 "])
    assert _read_icao24_or_escape() == "abc123"

    set_inputs(monkeypatch, ["esc"])
    assert _read_required_text_or_escape("value: ") is None
    set_inputs(monkeypatch, ["esc"])
    assert _read_icao24_or_escape() is None


def test_read_optional_float_or_escape_validates_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_inputs(monkeypatch, ["bad", "nan", "-1", "101", "50"])
    assert _read_optional_float_or_escape("value: ", 0, 100) == (False, 50.0)

    set_inputs(monkeypatch, [""])
    assert _read_optional_float_or_escape("value: ") == (False, None)
    set_inputs(monkeypatch, ["5"])
    assert _read_optional_float_or_escape("value: ") == (False, 5.0)
    set_inputs(monkeypatch, ["esc"])
    assert _read_optional_float_or_escape("value: ") == (True, None)

    output = capsys.readouterr().out
    assert "Введите число или оставьте поле пустым" in output
    assert "Введите конечное число" in output
    assert "не меньше 0" in output
    assert "не больше 100" in output


def test_read_console_value_fallback_recognizes_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module.os, "name", "posix")
    set_inputs(monkeypatch, ["value", "ESC", "\x1b"])

    assert _read_console_value_or_escape("value: ") == "value"
    assert _read_console_value_or_escape("value: ") is None
    assert _read_console_value_or_escape("value: ") is None


def test_read_console_value_handles_windows_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module.os, "name", "nt")
    monkeypatch.setattr(main_module.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    fake_msvcrt = SimpleNamespace(getwch=Mock())
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    fake_msvcrt.getwch.side_effect = ["\x1b"]
    assert _read_console_value_or_escape("value: ") is None

    fake_msvcrt.getwch.side_effect = ["a", "b", "\b", "c", "\r"]
    assert _read_console_value_or_escape("value: ") == "ac"

    fake_msvcrt.getwch.side_effect = ["\b", "\x00", "ignored", "z", "\n"]
    assert _read_console_value_or_escape("value: ") == "z"

    fake_msvcrt.getwch.side_effect = ["\x03"]
    with pytest.raises(KeyboardInterrupt):
        _read_console_value_or_escape("value: ")


def test_remove_existing_aircraft_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_path = tmp_path / "aircraft.json"
    file_path.write_text("old", encoding="utf-8")

    assert _remove_existing_aircraft_file(file_path) is True
    assert not file_path.exists()
    assert _remove_existing_aircraft_file(file_path) is True

    def fail_unlink(*args: object, **kwargs: object) -> None:
        raise OSError("нет доступа")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    assert _remove_existing_aircraft_file(file_path) is False
    assert "Не удалось удалить существующий файл" in capsys.readouterr().out


def test_user_interaction_removes_existing_file_after_country_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_path = tmp_path / "aircraft.json"
    file_path.write_text("old", encoding="utf-8")
    storage = JSONAircraftStorage(file_path)
    collector = Mock(spec=AirspaceCollector)
    collector.collect_country.side_effect = ValueError("страна не найдена")
    set_inputs(monkeypatch, ["Россия", "0"])

    user_interaction(collector, storage)

    assert not file_path.exists()
    assert "Не удалось получить данные" in capsys.readouterr().out


def test_user_interaction_retries_when_file_removal_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = JSONAircraftStorage(tmp_path / "aircraft.json")
    collector = Mock(spec=AirspaceCollector)
    remove_file = Mock(return_value=False)
    monkeypatch.setattr(main_module, "_remove_existing_aircraft_file", remove_file)
    set_inputs(monkeypatch, ["Россия", "0"])

    user_interaction(collector, storage)

    collector.collect_country.assert_not_called()


@pytest.mark.parametrize("error", [EOFError(), KeyboardInterrupt()])
def test_user_interaction_handles_interrupted_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: BaseException,
) -> None:
    monkeypatch.setattr("builtins.input", Mock(side_effect=error))

    user_interaction(Mock(spec=AirspaceCollector), Mock(spec=AbstractAircraftStorage))

    assert "Работа программы завершена" in capsys.readouterr().out


def test_user_interaction_handles_collector_value_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    collector = Mock(spec=AirspaceCollector)
    collector.collect_country.side_effect = ValueError("некорректная страна")
    set_inputs(monkeypatch, ["Ошибка", "0"])

    user_interaction(collector, Mock(spec=AbstractAircraftStorage))

    assert "Не удалось получить данные: некорректная страна" in capsys.readouterr().out


def test_main_builds_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    nominatim = Mock()
    opensky = Mock()
    collector = Mock()
    storage = Mock()
    nominatim_class = Mock(return_value=nominatim)
    opensky_class = Mock(return_value=opensky)
    collector_class = Mock(return_value=collector)
    storage_class = Mock(return_value=storage)
    interaction = Mock()
    monkeypatch.setattr(main_module, "NominatimAPI", nominatim_class)
    monkeypatch.setattr(main_module, "OpenSkyAPI", opensky_class)
    monkeypatch.setattr(main_module, "AirspaceCollector", collector_class)
    monkeypatch.setattr(main_module, "JSONAircraftStorage", storage_class)
    monkeypatch.setattr(main_module, "user_interaction", interaction)

    main_module.main()

    collector_class.assert_called_once_with(nominatim, opensky)
    interaction.assert_called_once_with(collector, storage)


def test_package_entry_point_calls_main(monkeypatch: pytest.MonkeyPatch) -> None:
    entry_point = Mock()
    monkeypatch.setattr(main_module, "main", entry_point)

    runpy.run_module("src.__main__", run_name="__main__")

    entry_point.assert_called_once_with()


def test_root_entry_point_calls_main(monkeypatch: pytest.MonkeyPatch) -> None:
    entry_point = Mock()
    monkeypatch.setattr(main_module, "main", entry_point)
    root_main = Path(__file__).parents[1] / "main.py"

    runpy.run_path(str(root_main), run_name="__main__")

    entry_point.assert_called_once_with()
