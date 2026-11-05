"""Консольное взаимодействие с пользователем."""

import os
import sys
import time
from collections.abc import Sequence
from math import isfinite
from pathlib import Path

from src.api import APIError, NominatimAPI, OpenSkyAPI
from src.interfaces import AirspaceService
from src.models import AircraftState, CountryAirspace
from src.service import AirspaceCollector
from src.storage import AbstractAircraftStorage, JSONAircraftStorage, StorageError


def get_top_aircraft_by_altitude(
    aircraft: Sequence[AircraftState], number: int, sort: bool = True
) -> list[AircraftState]:
    """Вернуть указанное количество воздушных судов с наибольшей или наименьшей высотой.

    Args:
        aircraft: последовательность объектов AircraftState, из которой формируется рейтинг, можно передать список,
            кортеж или другую последовательность. объекты с неизвестной высотой (altitude is None) не включаются в
            результат.
        number: максимальное количество воздушных судов, которое требуется вернуть. Значение должно быть положительным.
            При number <= 0 функция вызывает ValueError.
        sort: определение рейтинга: `True` - по наибольшей высоте (выбрано по умолчанию), `False` - по нименьшей высоте

    Returns:
        новый список воздушных судов, отсортированный по выбранному порядку. Если подходящих воздушных судов меньше,
            чем указано в `number`, возвращаются все найденные. Если ни у одного воздушного судна высота не определена,
            возвращается пустой список.
    """
    if number <= 0:
        raise ValueError("Количество воздушных судов должно быть положительным")

    aircraft_with_altitude = [item for item in aircraft if item.altitude is not None]
    return sorted(aircraft_with_altitude, key=_altitude_for_sorting, reverse=sort)[:number]


def get_aircraft_by_origin_country(aircraft: Sequence[AircraftState], country: str) -> list[AircraftState]:
    """Вернуть воздушные суда, страна регистрации которых совпадает с указанной.

    Args:
        aircraft: последовательность объектов AircraftState, среди которых выполняется поиск. Можно передать список,
            кортеж или другую последовательность.
        country: название страны регистрации. Пробелы в начале и конце удаляются, регистр символов не учитывается.
            Например, значения "Germany", "germany" и "  GeRmAnY  " считаются одинаковыми. Пустая строка вызывает
            ValueError.

    Returns:
          новый список воздушных судов, у которых атрибут origin_country совпадает с переданной страной;
            если совпадений нет, возвращается пустой список; исходная последовательность воздушных судов не изменяется.
    """

    normalized_country = country.strip().casefold()
    if not normalized_country:
        raise ValueError("Страна регистрации не может быть пустой")

    return [item for item in aircraft if item.origin_country.casefold() == normalized_country]


def user_interaction(collector: AirspaceService, storage: AbstractAircraftStorage) -> None:
    """Запустить консольный сценарий получения и обработки данных о воздушных судах."""

    print("Программа поиска воздушных судов в воздушном пространстве страны.")
    print("Чтобы завершить работу при вводе страны, введите 0.")

    try:
        while True:
            country_name = input("\nВведите название страны: ").strip()
            if country_name == "0":
                print("Работа программы завершена.")
                return
            if not country_name:
                print("Название страны не может быть пустым.")
                continue

            try:
                server_time, airspace = collector.collect_country(country_name)
            except (APIError, ValueError) as error:
                print(f"Не удалось получить данные: {error}")
                continue

            if isinstance(storage, JSONAircraftStorage) and not _remove_existing_aircraft_file(storage.file_path):
                continue

            print(f"\nСтрана: {airspace.country.name}")
            print(f"Время ответа OpenSky: {server_time}")
            print(f"Найдено воздушных судов: {len(airspace.aircraft)}")

            if not _aircraft_menu(server_time, airspace, storage):
                print("Работа программы завершена.")
                return
    except (EOFError, KeyboardInterrupt):
        print("\nРабота программы завершена.")


def _aircraft_menu(server_time: int, airspace: CountryAirspace, storage: AbstractAircraftStorage) -> bool:
    """Обработать меню; вернуть True, если пользователь хочет выбрать другую страну."""

    aircraft = airspace.aircraft
    while True:
        print("\nВыберите действие:")
        print("1. Показать топ воздушных судов по высоте")
        print("2. Найти воздушные суда по стране регистрации")
        print("3. Показать все найденные воздушные суда")
        print("4. Работа с файлами")
        print("5. Выполнить запрос для другой страны")
        print("0. Завершить работу")

        choice = input("Ваш выбор: ").strip()
        if choice == "1":
            _show_top_by_altitude(aircraft)
        elif choice == "2":
            _show_by_origin_country(aircraft)
        elif choice == "3":
            _print_aircraft(aircraft)
        elif choice == "4":
            if not isinstance(storage, JSONAircraftStorage):
                print("Работа с файлами доступна только для JSON-хранилища.")
                continue
            if not _file_menu(server_time, airspace, storage):
                return False
        elif choice == "5":
            return True
        elif choice == "0":
            return False
        else:
            print("Неизвестный пункт меню. Введите число от 0 до 5.")


def _show_top_by_altitude(aircraft: list[AircraftState]) -> None:
    """Запросить размер топа и вывести воздушные суда по убыванию высоты."""

    if not any(item.altitude is not None for item in aircraft):
        print("Нет воздушных судов с известной высотой.")
        return

    number = _read_positive_integer("Введите количество воздушных судов в топе: ")
    top_aircraft = get_top_aircraft_by_altitude(aircraft, number)
    print(f"\nТоп-{len(top_aircraft)} воздушных судов по высоте:")
    _print_aircraft(top_aircraft)


def _show_by_origin_country(aircraft: list[AircraftState]) -> None:
    """Запросить страну регистрации и вывести подходящие воздушные суда."""

    if not aircraft:
        print("Список воздушных судов пуст.")
        return

    available_countries = sorted({item.origin_country for item in aircraft}, key=str.casefold)
    print("Доступные страны регистрации:")
    print(", ".join(available_countries))

    country = input("Введите страну регистрации: ").strip()
    try:
        matching_aircraft = get_aircraft_by_origin_country(aircraft, country)
    except ValueError as error:
        print(error)
        return

    if not matching_aircraft:
        print(f"Воздушные суда со страной регистрации {country} не найдены.")
        return

    print(f"\nВоздушные суда со страной регистрации {country}:")
    _print_aircraft(matching_aircraft)


def _save_aircraft(server_time: int, airspace: CountryAirspace, storage: AbstractAircraftStorage) -> None:
    """Сохранить найденные воздушные суда в подключённое хранилище."""

    if isinstance(storage, JSONAircraftStorage) and storage.file_path.exists():
        print("Файл уже сохранен.")
        return

    if not airspace.aircraft:
        print("Нет воздушных судов для сохранения.")
        return

    try:
        storage.replace_airspace(server_time, airspace)
    except StorageError as error:
        print(f"Не удалось сохранить данные: {error}")
        return

    print(f"Сохранено воздушных судов: {len(airspace.aircraft)}")
    print("Файл успешно сформирован: data/aircraft.json")


def _file_menu(server_time: int, airspace: CountryAirspace, storage: JSONAircraftStorage) -> bool:
    """Обработать меню работы с JSON-файлом; False завершает программу."""

    while True:
        print("\nРабота с файлами:")
        print("1. Сохранить найденные воздушные суда в JSON")
        print("2. Удалить записи по фильтрам из файла")
        print("3. Добавить запись в файл")
        print("4. Вернуться")
        print("0. Завершить работу")

        choice = input("Ваш выбор: ").strip()
        if choice == "1":
            _save_aircraft(server_time, airspace, storage)
        elif choice == "2":
            if not storage.file_path.exists():
                print("Предварительно сохраните файл")
                continue
            _delete_aircraft_menu(storage)
        elif choice == "3":
            if not storage.file_path.exists():
                print("Предварительно сохраните файл")
                continue
            _add_aircraft(airspace, storage)
        elif choice == "4":
            return True
        elif choice == "0":
            return False
        else:
            print("Неизвестный пункт меню. Введите число от 0 до 4.")


def _delete_aircraft_menu(storage: JSONAircraftStorage) -> None:
    """Удалять записи из JSON-файла по выбранному пользователем фильтру."""

    filters = {
        "1": ("origin_country", "Введите страну регистрации: "),
        "2": ("icao24", "Введите значение icao24: "),
        "3": ("callsign", "Введите значение callsign: "),
    }
    while True:
        print("\nУдаление записей:")
        print("1. По стране регистрации")
        print("2. По коду icao24")
        print("3. По коду callsign")
        print("4. Отменить")

        choice = input("Ваш выбор: ").strip()
        if choice == "4":
            return
        if choice not in filters:
            print("Неизвестный пункт меню. Введите число от 1 до 4.")
            continue

        field_name, prompt = filters[choice]
        value = input(prompt).strip()
        if not value:
            print("Значение фильтра не может быть пустым.")
            continue
        if field_name == "icao24":
            value = "".join(value.split()).lower()

        try:
            deleted_count = storage.delete_aircraft({field_name: value})
            saved_count = len(storage.get_aircraft())
        except (StorageError, TypeError, ValueError) as error:
            print(f"Не удалось удалить записи: {error}")
            continue

        print(f"Удалено {deleted_count}, сохранено {saved_count}.")


def _add_aircraft(airspace: CountryAirspace, storage: JSONAircraftStorage) -> None:
    """Запросить параметры воздушного судна и добавить его в JSON-файл."""

    coordinates = _read_aircraft_coordinates(airspace)
    if coordinates is None:
        return
    longitude, latitude = coordinates

    aircraft = _read_aircraft_state(longitude, latitude)
    if aircraft is None:
        return

    try:
        storage.add_aircraft(aircraft)
    except StorageError as error:
        print(f"Не удалось добавить запись: {error}")
        return

    print(f"В файл {storage.file_path} добавлено 1 записей.")


def _read_aircraft_state(longitude: float, latitude: float) -> AircraftState | None:
    """Получить параметры и сформировать проверенный объект воздушного судна."""

    print("Введите основные параметры воздушного судна (прервать ввод и вернуться введите 'esc')")
    origin_country = _read_required_text_or_escape("Введите origin_country: ")
    if origin_country is None:
        return None
    icao24 = _read_icao24_or_escape()
    if icao24 is None:
        return None
    callsign = _read_required_text_or_escape("Введите callsign: ", remove_spaces=True)
    if callsign is None:
        return None

    numeric_values = _read_optional_aircraft_numbers()
    if numeric_values is None:
        return None

    squawk_value = _read_console_value_or_escape("Введите squawk: ")
    if squawk_value is None:
        return None
    squawk = squawk_value.strip() or None
    timestamp = int(time.time())

    try:
        return AircraftState(
            icao24=icao24,
            callsign=callsign,
            origin_country=origin_country,
            time_position=timestamp,
            last_contact=timestamp,
            longitude=longitude,
            latitude=latitude,
            baro_altitude=numeric_values["baro_altitude"],
            on_ground=False,
            velocity=numeric_values["velocity"],
            true_track=numeric_values["true_track"],
            vertical_rate=numeric_values["vertical_rate"],
            sensors=None,
            geo_altitude=numeric_values["geo_altitude"],
            squawk=squawk,
            spi=False,
            position_source=0,
        )
    except (TypeError, ValueError) as error:
        print(f"Не удалось добавить запись: {error}")
        return None


def _read_optional_aircraft_numbers() -> dict[str, float | None] | None:
    """Получить необязательные числовые параметры или отменить создание записи."""

    specifications: tuple[tuple[str, str, float | None, float | None], ...] = (
        ("baro_altitude", "Введите baro_altitude: ", 0, 30_000),
        ("geo_altitude", "Введите geo_altitude: ", 0, 30_000),
        ("velocity", "Введите velocity: ", 0, None),
        ("vertical_rate", "Введите vertical_rate: ", 0, None),
        ("true_track", "Введите true_track: ", 0, 360),
    )
    values: dict[str, float | None] = {}
    for name, prompt, minimum, maximum in specifications:
        cancelled, value = _read_optional_float_or_escape(prompt, minimum, maximum)
        if cancelled:
            return None
        values[name] = value
    return values


def _read_aircraft_coordinates(airspace: CountryAirspace) -> tuple[float, float] | None:
    """Получить координаты внутри прямоугольных границ обрабатываемой страны."""

    while True:
        print("Введите долготу и широту воздушного судна:")
        longitude = _read_float_in_range("Введите longitude: ", -180, 180)
        latitude = _read_float_in_range("Введите latitude: ", -90, 90)
        if airspace.country.bounding_box.contains(latitude, longitude):
            return longitude, latitude

        print(f"Введенные координаты не соответствуют обрабатываемой стране {airspace.country.name}")
        while True:
            print("1. Определить координаты заново")
            print("0. Вернуться в меню работы с файлами")
            choice = input("Ваш выбор: ").strip()
            if choice == "1":
                break
            if choice == "0":
                return None
            print("Неизвестный пункт меню. Введите 1 или 0.")


def _read_float_in_range(prompt: str, minimum: float, maximum: float) -> float:
    """Запрашивать обязательное число, пока оно не попадёт в заданный диапазон."""

    while True:
        raw_value = input(prompt).strip()
        if not raw_value:
            print("Значение не может быть пустым.")
            continue
        try:
            value = float(raw_value)
        except ValueError:
            print("Введите число.")
            continue
        if not isfinite(value):
            print("Введите конечное число.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"Значение должно находиться в диапазоне от {minimum:g} до {maximum:g}.")


def _read_required_text_or_escape(prompt: str, remove_spaces: bool = False) -> str | None:
    """Получить обязательный текст или None или Esc."""

    while True:
        raw_value = _read_console_value_or_escape(prompt)
        if raw_value is None:
            return None
        value = "".join(raw_value.split()) if remove_spaces else raw_value.strip()
        if value:
            return value
        print("Значение не может быть пустым или состоять только из пробелов.")


def _read_icao24_or_escape() -> str | None:
    """Получить нормализованный шестизначный ICAO24 или отменить ввод."""

    while True:
        value = _read_required_text_or_escape("Введите icao24: ", remove_spaces=True)
        if value is None:
            return None
        normalized = value.lower()
        if len(normalized) == 6 and all(symbol in "0123456789abcdef" for symbol in normalized):
            return normalized
        print("icao24 должен содержать 6 шестнадцатеричных символов.")


def _read_optional_float_or_escape(
    prompt: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[bool, float | None]:
    """Получить необязательное число; первый элемент результата сообщает об отмене."""

    while True:
        raw_value = _read_console_value_or_escape(prompt)
        if raw_value is None:
            return True, None
        if not raw_value.strip():
            return False, None
        try:
            value = float(raw_value)
        except ValueError:
            print("Введите число или оставьте поле пустым.")
            continue
        if not isfinite(value):
            print("Введите конечное число или оставьте поле пустым.")
            continue
        if minimum is not None and value < minimum:
            print(f"Значение должно быть не меньше {minimum:g}.")
            continue
        if maximum is not None and value > maximum:
            print(f"Значение должно быть не больше {maximum:g}.")
            continue
        return False, value


def _read_console_value_or_escape(prompt: str) -> str | None:
    """Прочитать строку и немедленно вернуть None при физическом нажатии Esc."""

    if os.name != "nt" or not sys.stdin.isatty():
        value = input(prompt)
        return None if value == "\x1b" or value.casefold() == "esc" else value

    import msvcrt

    print(prompt, end="", flush=True)
    characters: list[str] = []
    while True:
        character = msvcrt.getwch()
        if character == "\x1b":
            print()
            return None
        if character in {"\r", "\n"}:
            print()
            return "".join(characters)
        if character == "\x03":
            raise KeyboardInterrupt
        if character == "\b":
            if characters:
                characters.pop()
                print("\b \b", end="", flush=True)
            continue
        if character in {"\x00", "\xe0"}:
            msvcrt.getwch()
            continue
        characters.append(character)
        print(character, end="", flush=True)


def _remove_existing_aircraft_file(file_path: Path) -> bool:
    """Удалить прежний JSON-файл после успешного запроса и сообщить об ошибке."""

    try:
        file_path.unlink(missing_ok=True)
    except OSError as error:
        print(f"Не удалось удалить существующий файл {file_path}: {error}")
        return False
    return True


def _read_positive_integer(prompt: str) -> int:
    """Запрашивать значение, пока пользователь не введёт положительное целое число."""

    while True:
        value = input(prompt).strip()
        try:
            number = int(value)
        except ValueError:
            print("Введите положительное целое число.")
            continue

        if number > 0:
            return number
        print("Введите положительное целое число.")


def _print_aircraft(aircraft: Sequence[AircraftState]) -> None:
    """Вывести основные сведения о воздушных судах."""

    if not aircraft:
        print("Воздушные суда не найдены.")
        return

    for position, item in enumerate(aircraft, start=1):
        callsign = item.callsign or "без позывного"
        altitude = f"{item.altitude:.1f} м" if item.altitude is not None else "нет данных"
        velocity = f"{item.velocity:.1f} м/с" if item.velocity is not None else "нет данных"
        longitude = f"{item.longitude:.4f}" if item.longitude is not None else "нет данных"
        latitude = f"{item.latitude:.4f}" if item.latitude is not None else "нет данных"
        print(
            f"{position}. {callsign} | ICAO24: {item.icao24} | "
            f"страна регистрации: {item.origin_country} | longitude: {longitude} | latitude: {latitude} | "
            f"высота: {altitude} | скорость: {velocity}"
        )


def _altitude_for_sorting(aircraft: AircraftState) -> float:
    """Вернуть числовую высоту для сортировки.

    Args:
        aircraft: объект с информацией об одном воздушном судне

    Returns:
        если высота известна - возвращается её числовое значение, если высота равна None - возвращается отрицательная
        бесконечность (`float("-inf")`):
    """

    altitude = aircraft.altitude
    return altitude if altitude is not None else float("-inf")


def main() -> None:
    """Создать зависимости и запустить консольное приложение."""

    # Создаётся JSON-хранилище
    storage = JSONAircraftStorage()

    # Создает Создаётся объект AirspaceCollector, в конструктор передаются оба API-клиента
    collector = AirspaceCollector(NominatimAPI(), OpenSkyAPI())

    # Запускается функция взаимодействия с пользователем
    user_interaction(collector, storage)
