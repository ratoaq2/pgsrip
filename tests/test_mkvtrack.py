import pytest

from pgsrip.mkv import MkvTrack

from . import from_yaml


def parameters_from_yaml(test_filename: str):
    data = from_yaml(test_filename)

    for scenario in data:
        yield scenario['track'], scenario['expected']


@pytest.mark.parametrize('track, expected', parameters_from_yaml(__file__))
def test_scenarios(track, expected):
    # given

    # when
    actual = MkvTrack(track)

    # then
    assert actual.to_dict() == expected
