"""Tests for the common, Nominatim, and OpenSky API clients."""

from email.message import Message
from io import BytesIO
from typing import Any
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

import src.api as api_module
from src.api import AbstractAPIClient, APIError, NominatimAPI, OpenSkyAPI
from src.models import AircraftState, BoundingBox


class ConcreteAPIClient(AbstractAPIClient):
    """Concrete implementation used to exercise the abstract transport."""

    def connect(self) -> bool:
        return True


class FakeResponse:
    """Minimal context manager compatible with urllib responses."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.data


def aircraft_vector(**changes: Any) -> list[Any]:
    values: list[Any] = [
        "abc123",
        " TEST1 ",
        "Testland",
        100,
        101,
        35.0,
        15.0,
        10_000.0,
        False,
        200.0,
        90.0,
        1.5,
        [1, 2],
        10_100.0,
        "7000",
        True,
        0,
    ]
    for index, value in changes.items():
        values[int(index)] = value
    return values


def test_abstract_client_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        AbstractAPIClient("https://example.com")  # type: ignore[abstract]


def test_common_client_builds_request_and_decodes_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["header"] = request.get_header("X-test")
        captured["timeout"] = timeout
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(api_module, "urlopen", fake_urlopen)
    client = ConcreteAPIClient("https://example.com///", timeout=5)

    assert client.connect()
    assert client.base_url == "https://example.com"
    assert client._request_json("/items", {"page": 2}, {"X-test": "yes"}) == {"ok": True}
    assert captured == {
        "url": "https://example.com/items?page=2",
        "header": "yes",
        "timeout": 5,
    }

    assert client._request_json("status") == {"ok": True}


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (HTTPError("url", 429, "limit", Message(), BytesIO()), "HTTP 429"),
        (URLError("offline"), "offline"),
        (TimeoutError(), "API не ответило"),
    ],
)
def test_common_client_converts_network_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    message: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> FakeResponse:
        raise error

    monkeypatch.setattr(api_module, "urlopen", fail)

    with pytest.raises(APIError, match=message):
        ConcreteAPIClient("https://example.com")._request_json("status")


def test_common_client_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_module, "urlopen", lambda *args, **kwargs: FakeResponse(b"not json"))

    with pytest.raises(APIError, match="некорректные данные"):
        ConcreteAPIClient("https://example.com")._request_json("status")


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"status": 0}, True),
        ({"status": 1}, False),
        ([], False),
    ],
)
def test_nominatim_connect(response: object, expected: bool) -> None:
    client = NominatimAPI()
    setattr(client, "_request", Mock(return_value=response))

    assert client.connect() is expected


def test_nominatim_gets_country_and_uses_memory_cache() -> None:
    response = [
        {
            "display_name": "Testland",
            "lat": "15.0",
            "lon": "35.0",
            "boundingbox": ["10", "20", "30", "40"],
            "address": {"country_code": "tl"},
        }
    ]
    client = NominatimAPI()
    request = Mock(return_value=response)
    setattr(client, "_request", request)

    first = client.get_data(" Testland ")
    second = client.get_data("testland")

    assert first is second
    assert first.name == "Testland"
    assert first.country_code == "TL"
    assert first.latitude == 15
    assert first.longitude == 35
    assert first.bounding_box == BoundingBox(10, 20, 30, 40)
    request.assert_called_once()


def test_nominatim_accepts_missing_optional_address_data() -> None:
    client = NominatimAPI()
    setattr(
        client,
        "_request",
        Mock(
            return_value=[
                {
                    "lat": 15,
                    "lon": 35,
                    "boundingbox": [10, 20, 30, 40],
                    "address": "not a mapping",
                }
            ]
        ),
    )

    country = client.get_data("Fallback name")

    assert country.name == "Fallback name"
    assert country.country_code is None


def test_nominatim_accepts_address_without_country_code() -> None:
    client = NominatimAPI()
    setattr(
        client,
        "_request",
        Mock(
            return_value=[
                {
                    "lat": 15,
                    "lon": 35,
                    "boundingbox": [10, 20, 30, 40],
                    "address": {},
                }
            ]
        ),
    )

    assert client.get_data("Testland").country_code is None


def test_nominatim_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="не может быть пустым"):
        NominatimAPI().get_data("   ")


@pytest.mark.parametrize("response", [None, [], ["invalid"]])
def test_nominatim_rejects_invalid_search_response(response: object) -> None:
    client = NominatimAPI()
    setattr(client, "_request", Mock(return_value=response))

    with pytest.raises(APIError, match="Страна не найдена"):
        client.get_data("Testland")


@pytest.mark.parametrize(
    "bounding_box",
    [None, ["10", "20", "30"]],
)
def test_nominatim_rejects_missing_bounding_box(bounding_box: object) -> None:
    client = NominatimAPI()
    setattr(client, "_request", Mock(return_value=[{"boundingbox": bounding_box}]))

    with pytest.raises(APIError, match="не вернул границы"):
        client.get_data("Testland")


@pytest.mark.parametrize(
    "item",
    [
        {"lon": 35, "boundingbox": [10, 20, 30, 40]},
        {"lat": "bad", "lon": 35, "boundingbox": [10, 20, 30, 40]},
        {"lat": 15, "lon": 35, "boundingbox": [20, 10, 30, 40]},
    ],
)
def test_nominatim_rejects_invalid_coordinates(item: dict[str, object]) -> None:
    client = NominatimAPI()
    setattr(client, "_request", Mock(return_value=[item]))

    with pytest.raises(APIError, match="некорректные координаты"):
        client.get_data("Testland")


def test_nominatim_request_waits_and_always_updates_time(monkeypatch: pytest.MonkeyPatch) -> None:
    client = NominatimAPI(user_agent="test-agent")
    client._last_request_time = 10.0
    request = Mock(return_value={"ok": True})
    sleep = Mock()
    monotonic = Mock(side_effect=[10.25, 11.0])
    monkeypatch.setattr(client, "_request_json", request)
    monkeypatch.setattr(api_module.time, "sleep", sleep)
    monkeypatch.setattr(api_module.time, "monotonic", monotonic)

    assert client._request("status", {"format": "json"}) == {"ok": True}
    sleep.assert_called_once_with(0.75)
    request.assert_called_once_with("status", {"format": "json"}, {"User-Agent": "test-agent"})
    assert client._last_request_time == 11.0

    client._last_request_time = 10.0
    monotonic.side_effect = [12.0, 13.0]
    request.side_effect = APIError("failed")
    sleep.reset_mock()
    with pytest.raises(APIError, match="failed"):
        client._request("status", {})
    sleep.assert_not_called()
    assert client._last_request_time == 13.0


def test_opensky_initialization_and_connect() -> None:
    client = OpenSkyAPI("https://example.com/", timeout=7)

    assert client.base_url == "https://example.com"
    assert client.timeout == 7
    assert client.connect()


@pytest.mark.parametrize("response", [None, []])
def test_opensky_rejects_non_mapping_response(response: object) -> None:
    client = OpenSkyAPI()
    setattr(client, "_request_json", Mock(return_value=response))

    with pytest.raises(APIError, match="неожиданный ответ"):
        client.get_data(BoundingBox(10, 20, 30, 40))


def test_opensky_rejects_invalid_states() -> None:
    client = OpenSkyAPI()
    setattr(client, "_request_json", Mock(return_value={"time": 123, "states": "invalid"}))

    with pytest.raises(APIError, match="некорректный список"):
        client.get_data(BoundingBox(10, 20, 30, 40))


@pytest.mark.parametrize("server_time", [None, True])
def test_opensky_rejects_invalid_server_time(server_time: object) -> None:
    client = OpenSkyAPI()
    setattr(client, "_request_json", Mock(return_value={"time": server_time, "states": []}))

    with pytest.raises(APIError, match="время сервера"):
        client.get_data(BoundingBox(10, 20, 30, 40))


@pytest.mark.parametrize(
    "response",
    [{"time": 123}, {"time": 123, "states": None}, {"time": 123, "states": []}],
)
def test_opensky_accepts_empty_states(response: dict[str, object]) -> None:
    client = OpenSkyAPI()
    setattr(client, "_request_json", Mock(return_value=response))

    assert client.get_data(BoundingBox(10, 20, 30, 40)) == (123, [])


def test_opensky_filters_and_returns_aircraft() -> None:
    client = OpenSkyAPI()
    request = Mock(
        return_value={
            "time": 123,
            "states": [
                "invalid",
                aircraft_vector(**{"8": True}),
                aircraft_vector(**{"5": "bad"}),
                aircraft_vector(**{"5": 50.0}),
                aircraft_vector(),
            ],
        }
    )
    setattr(client, "_request_json", request)
    bounding_box = BoundingBox(10, 20, 30, 40)

    server_time, result = client.get_data(bounding_box)

    assert server_time == 123
    assert len(result) == 1
    assert result[0].icao24 == "abc123"
    request.assert_called_once_with(
        "states/all",
        {"extended": 1, "lamin": "10", "lamax": "20", "lomin": "30", "lomax": "40"},
    )

    setattr(
        client,
        "_request_json",
        Mock(return_value={"time": 124, "states": [aircraft_vector(**{"8": True})]}),
    )
    server_time, result = client.get_data(bounding_box, airborne_only=False)
    assert server_time == 124
    assert len(result) == 1


@pytest.mark.parametrize(
    "item",
    [
        "not a list",
        ["too", "short"],
        aircraft_vector(**{"0": 123}),
        aircraft_vector(**{"2": 123}),
        aircraft_vector(**{"5": None}),
        aircraft_vector(**{"6": None}),
        aircraft_vector(**{"8": "false"}),
    ],
)
def test_parse_aircraft_rejects_invalid_required_data(item: object) -> None:
    assert OpenSkyAPI._parse_aircraft(item) is None


def test_parse_aircraft_maps_all_fields() -> None:
    state = OpenSkyAPI._parse_aircraft(aircraft_vector(**{"7": None, "12": [1, True, "2"]}))

    assert state == AircraftState(
        icao24="abc123",
        callsign="TEST1",
        origin_country="Testland",
        time_position=100,
        last_contact=101,
        longitude=35.0,
        latitude=15.0,
        baro_altitude=None,
        on_ground=False,
        velocity=200.0,
        true_track=90.0,
        vertical_rate=1.5,
        sensors=[1, 2],
        geo_altitude=10_100.0,
        squawk="7000",
        spi=True,
        position_source=0,
    )


def test_parse_aircraft_handles_optional_invalid_values() -> None:
    state = OpenSkyAPI._parse_aircraft(
        aircraft_vector(
            **{
                "1": 123,
                "3": True,
                "4": "bad",
                "7": True,
                "9": "bad",
                "10": None,
                "11": "bad",
                "12": "bad",
                "13": "bad",
                "14": 7000,
                "15": "true",
                "16": "bad",
            }
        )
    )

    assert state is not None
    assert state.callsign is None
    assert state.time_position is None
    assert state.last_contact is None
    assert state.baro_altitude is None
    assert state.velocity is None
    assert state.true_track is None
    assert state.vertical_rate is None
    assert state.sensors is None
    assert state.geo_altitude is None
    assert state.squawk is None
    assert not state.spi
    assert state.position_source is None


def test_parse_aircraft_catches_conversion_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(value: object) -> int | None:
        raise TypeError("conversion failed")

    monkeypatch.setattr(OpenSkyAPI, "_to_int", fail)

    assert OpenSkyAPI._parse_aircraft(aircraft_vector()) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (True, None), ("1.5", 1.5), ("bad", None)],
)
def test_to_float(value: object, expected: float | None) -> None:
    assert OpenSkyAPI._to_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (True, None), ("2", 2), ("bad", None)],
)
def test_to_int(value: object, expected: int | None) -> None:
    assert OpenSkyAPI._to_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ([1, True, "2"], [1, 2]), (["bad"], None)],
)
def test_to_int_list(value: object, expected: list[int] | None) -> None:
    assert OpenSkyAPI._to_int_list(value) == expected
