"""Tests for the project data models."""

import pytest

from src.models import BoundingBox


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
