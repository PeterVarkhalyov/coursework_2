"""Консольное взаимодействие с пользователем."""

from collections.abc import Sequence

from src.api import APIError, NominatimAPI, OpenSkyAPI
from src.models import AircraftState
from src.storage import AbstractAircraftStorage, JSONAircraftStorage, StorageError


def get_top_aircraft_by_altitude(aircraft: Sequence[AircraftState], number: int) -> list[AircraftState]:
    """Вернуть указанное количество воздушных судов с наибольшей высотой."""

    if number <= 0:
        raise ValueError("Количество воздушных судов должно быть положительным")

    aircraft_with_altitude = [item for item in aircraft if item.altitude is not None]
    return sorted(aircraft_with_altitude, key=_altitude_for_sorting, reverse=True)[:number]


def get_aircraft_by_origin_country(aircraft: Sequence[AircraftState], country: str) -> list[AircraftState]:
    """Вернуть воздушные суда, страна регистрации которых совпадает с указанной."""

    normalized_country = country.strip().casefold()
    if not normalized_country:
        raise ValueError("Страна регистрации не может быть пустой")

    return [item for item in aircraft if item.origin_country.casefold() == normalized_country]


def user_interaction(
    nominatim: NominatimAPI | None = None,
    opensky: OpenSkyAPI | None = None,
    storage: AbstractAircraftStorage | None = None,
) -> None:
    """Запустить консольный сценарий получения и обработки данных о воздушных судах."""

    nominatim_client = nominatim if nominatim is not None else NominatimAPI()
    opensky_client = opensky if opensky is not None else OpenSkyAPI()
    aircraft_storage = storage if storage is not None else JSONAircraftStorage()

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
                country = nominatim_client.get_data(country_name)
                server_time, aircraft = opensky_client.get_data(country.bounding_box)
            except (APIError, ValueError) as error:
                print(f"Не удалось получить данные: {error}")
                continue

            print(f"\nСтрана: {country.name}")
            print(f"Время ответа OpenSky: {server_time}")
            print(f"Найдено воздушных судов: {len(aircraft)}")

            if not _aircraft_menu(aircraft, aircraft_storage):
                print("Работа программы завершена.")
                return
    except (EOFError, KeyboardInterrupt):
        print("\nРабота программы завершена.")


def _aircraft_menu(aircraft: list[AircraftState], storage: AbstractAircraftStorage) -> bool:
    """Обработать меню; вернуть True, если пользователь хочет выбрать другую страну."""

    while True:
        print("\nВыберите действие:")
        print("1. Показать топ воздушных судов по высоте")
        print("2. Найти воздушные суда по стране регистрации")
        print("3. Показать все найденные воздушные суда")
        print("4. Сохранить найденные воздушные суда в JSON")
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
            _save_aircraft(aircraft, storage)
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


def _save_aircraft(aircraft: list[AircraftState], storage: AbstractAircraftStorage) -> None:
    """Сохранить найденные воздушные суда в подключённое хранилище."""

    if not aircraft:
        print("Нет воздушных судов для сохранения.")
        return

    try:
        storage.replace_aircraft(aircraft)
    except StorageError as error:
        print(f"Не удалось сохранить данные: {error}")
        return

    print(f"Сохранено воздушных судов: {len(aircraft)}")


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
        print(
            f"{position}. {callsign} | ICAO24: {item.icao24} | "
            f"страна регистрации: {item.origin_country} | высота: {altitude} | скорость: {velocity}"
        )


def _altitude_for_sorting(aircraft: AircraftState) -> float:
    """Вернуть числовую высоту для сортировки."""

    altitude = aircraft.altitude
    return altitude if altitude is not None else float("-inf")


def main() -> None:
    """Точка входа консольного приложения."""

    user_interaction()


if __name__ == "__main__":
    main()
