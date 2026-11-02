"""Классы для хранения информации о воздушных судах в файлах."""

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import fields
from json import JSONDecodeError
from pathlib import Path
from typing import Any, cast

from src.models import AircraftState, CountryAirspace


class StorageError(Exception):
    """Ошибка чтения, проверки или записи данных хранилища."""


class AbstractAircraftStorage(ABC):
    """Абстрактный интерфейс хранилища информации о воздушных судах.

    Конкретные коннекторы обязаны реализовать добавление воздушного судна,
    получение воздушного судна по критериям и удаление подходящих записей.
    Благодаря общему интерфейсу JSON-файл в дальнейшем можно заменить CSV, Excel,
    базой данных или удалённым хранилищем.
    """

    @abstractmethod
    def add_aircraft(self, aircraft: AircraftState) -> None:
        """Добавить информацию об одном воздушном судне в хранилище."""

    @abstractmethod
    def replace_aircraft(self, aircraft: Sequence[AircraftState]) -> None:
        """Полностью заменить содержимое хранилища переданными воздушными судами."""

    @abstractmethod
    def replace_airspace(self, server_time: int, airspace: CountryAirspace) -> None:
        """Сохранить время сервера, страну и найденные воздушные суда."""

    @abstractmethod
    def get_aircraft(self, criteria: Mapping[str, object] | None = None) -> list[AircraftState]:
        """Получить воздушные суда, атрибуты которых соответствуют критериям."""

    @abstractmethod
    def delete_aircraft(self, criteria: Mapping[str, object]) -> int:
        """Удалить подходящие записи и вернуть количество удалённых воздушных судов."""


class JSONAircraftStorage(AbstractAircraftStorage):
    """Хранилище информации о воздушных судах в JSON-файле.

    Attributes:
        file_path: путь к JSON-файлу. Если файл ещё не создан,
            при чтении хранилище считается пустым.

    Methods:
        add_aircraft(): добавляет объект AircraftState в конец JSON-списка.
        replace_aircraft(): заменяет содержимое файла переданным списком.
        replace_airspace(): сохраняет полный снимок воздушного пространства.
        get_aircraft(): возвращает все записи или записи по критериям.
        delete_aircraft(): удаляет записи по заданным критериям.
    """

    DEFAULT_FILE_PATH = Path("data/aircraft.json")
    AIRCRAFT_FIELDS = frozenset(field.name for field in fields(AircraftState))

    def __init__(self, file_path: str | Path = DEFAULT_FILE_PATH) -> None:
        self.file_path = Path(file_path)

    def add_aircraft(self, aircraft: AircraftState) -> None:
        """Добавить информацию об одном воздушном судне в JSON-файл."""

        if not isinstance(aircraft, AircraftState):
            raise TypeError("aircraft должен быть объектом AircraftState")

        document = self._read_document()
        records = document["country"]["aircraft"]
        records.append(aircraft.to_dict())
        document["country"]["count_aircraft"] = len(records)
        self._write_document(document)

    def replace_aircraft(self, aircraft: Sequence[AircraftState]) -> None:
        """Полностью заменить содержимое JSON-файла одной операцией записи."""

        aircraft_list = list(aircraft)
        if any(not isinstance(item, AircraftState) for item in aircraft_list):
            raise TypeError("Все элементы aircraft должны быть объектами AircraftState")

        self._write_records([item.to_dict() for item in aircraft_list])

    def replace_airspace(self, server_time: int, airspace: CountryAirspace) -> None:
        """Полностью заменить файл снимком воздушного пространства страны."""

        if isinstance(server_time, bool) or not isinstance(server_time, int) or server_time < 0:
            raise ValueError("server_time должен быть неотрицательным целым числом")
        if not isinstance(airspace, CountryAirspace):
            raise TypeError("airspace должен быть объектом CountryAirspace")
        if any(not isinstance(item, AircraftState) for item in airspace.aircraft):
            raise TypeError("airspace.aircraft должен содержать объекты AircraftState")

        records = [item.to_dict() for item in airspace.aircraft]
        document = self._build_document(
            records,
            server_time=server_time,
            country_name=airspace.country.name,
            country_code=airspace.country.country_code,
        )
        self._write_document(document)

    def get_aircraft(self, criteria: Mapping[str, object] | None = None) -> list[AircraftState]:
        """Получить воздушное судно, подходящие под все переданные критерии.

        Если criteria не передан или является пустым словарём, метод
        возвращает все воздушные суда из файла.
        """

        normalized_criteria = self._validate_criteria(criteria)
        aircraft = [self._to_aircraft(record) for record in self._read_records()]
        return [item for item in aircraft if self._matches(item, normalized_criteria)]

    def delete_aircraft(self, criteria: Mapping[str, object]) -> int:
        """Удалить воздушное судно по критериям и вернуть число удалённых записей.

        Пустые критерии запрещены, поскольку они могли бы случайно удалить
        всю информацию из файла.
        """

        normalized_criteria = self._validate_criteria(criteria)
        if not normalized_criteria:
            raise ValueError("Для удаления необходимо указать хотя бы один критерий")

        aircraft = [self._to_aircraft(record) for record in self._read_records()]
        remaining = [item for item in aircraft if not self._matches(item, normalized_criteria)]
        deleted_count = len(aircraft) - len(remaining)

        if deleted_count:
            document = self._read_document()
            document["country"]["aircraft"] = [item.to_dict() for item in remaining]
            document["country"]["count_aircraft"] = len(remaining)
            self._write_document(document)

        return deleted_count

    def _read_records(self) -> list[dict[str, Any]]:
        """Прочитать и проверить список записей из JSON-файла."""

        document = self._read_document()
        return cast(list[dict[str, Any]], document["country"]["aircraft"])

    def _read_document(self) -> dict[str, Any]:
        """Прочитать и проверить документ воздушного пространства."""

        if not self.file_path.exists():
            return self._build_document([])

        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as error:
            raise StorageError(f"Не удалось прочитать JSON-файл: {self.file_path}") from error

        return self._validate_document(data)

    @classmethod
    def _validate_document(cls, data: object) -> dict[str, Any]:
        """Проверить корневые поля документа и вернуть типизированный словарь."""

        if not isinstance(data, dict):
            raise StorageError("JSON-файл должен содержать объект воздушного пространства")

        cls._get_non_negative_integer(data.get("time"), "JSON-файл содержит некорректное поле time")

        country = data.get("country")
        if not isinstance(country, dict):
            raise StorageError("JSON-файл содержит некорректное поле country")

        cls._validate_country(country)
        return cast(dict[str, Any], data)

    @classmethod
    def _validate_country(cls, country: dict[object, object]) -> None:
        """Проверить метаданные страны и список воздушных судов."""

        name = country.get("name")
        country_code = country.get("country_code")
        if not isinstance(name, str):
            raise StorageError("JSON-файл содержит некорректное название страны")
        if country_code is not None and not isinstance(country_code, str):
            raise StorageError("JSON-файл содержит некорректный код страны")

        count_aircraft = cls._get_non_negative_integer(
            country.get("count_aircraft"),
            "JSON-файл содержит некорректное количество самолётов",
        )
        records = country.get("aircraft")
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            raise StorageError("JSON-файл содержит некорректный список самолётов")
        if count_aircraft != len(records):
            raise StorageError("Количество самолётов не совпадает с длиной списка")

    @staticmethod
    def _get_non_negative_integer(value: object, error_message: str) -> int:
        """Вернуть неотрицательное целое число или вызвать StorageError."""

        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise StorageError(error_message)
        return value

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        """Записать список объектов в JSON-файл."""

        self._write_document(self._build_document(records))

    def _write_document(self, document: dict[str, Any]) -> None:
        """Записать документ воздушного пространства в JSON-файл."""

        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(document, ensure_ascii=False, indent=2)
            self.file_path.write_text(content, encoding="utf-8")
        except (OSError, TypeError, ValueError) as error:
            raise StorageError(f"Не удалось записать JSON-файл: {self.file_path}") from error

    @staticmethod
    def _build_document(
        records: list[dict[str, Any]],
        server_time: int = 0,
        country_name: str = "",
        country_code: str | None = None,
    ) -> dict[str, Any]:
        """Сформировать документ в формате хранения воздушного пространства."""

        return {
            "time": server_time,
            "country": {
                "name": country_name,
                "country_code": country_code,
                "count_aircraft": len(records),
                "aircraft": records,
            },
        }

    def _to_aircraft(self, record: dict[str, Any]) -> AircraftState:
        """Преобразовать словарь из файла в проверенный объект AircraftState."""

        try:
            return AircraftState(**record)
        except (TypeError, ValueError) as error:
            raise StorageError("JSON-файл содержит некорректную запись о самолёте") from error

    def _validate_criteria(self, criteria: Mapping[str, object] | None) -> dict[str, object]:
        """Проверить критерии и вернуть их копию."""

        if criteria is None:
            return {}
        if not isinstance(criteria, Mapping):
            raise TypeError("criteria должен быть словарём или другим отображением")

        unknown_fields = set(criteria) - self.AIRCRAFT_FIELDS
        if unknown_fields:
            fields_text = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Неизвестные критерии поиска: {fields_text}")

        return dict(criteria)

    @staticmethod
    def _matches(aircraft: AircraftState, criteria: Mapping[str, object]) -> bool:
        """Проверить совпадение всех атрибутов воздушного судна с критериями."""

        return all(getattr(aircraft, name) == value for name, value in criteria.items())


class CSVAircraftStorage(AbstractAircraftStorage):
    """Хранилище информации о воздушных судах в CSV-файле."""

    pass


class TXTAircraftStorage(AbstractAircraftStorage):
    """Хранилище информации о воздушных судах в TXT-файле."""

    pass


class XLSXAircraftStorage(AbstractAircraftStorage):
    """Хранилище информации о воздушных судах в XLSX-файле."""

    pass


class SQLAircraftStorage(AbstractAircraftStorage):
    """Хранилище информации о воздушных судах в Базе данных."""

    pass
