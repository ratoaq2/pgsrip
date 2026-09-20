import pytest

from pgsrip.mkv import MkvTrack
from pgsrip.track_flags import TrackFlags

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


def _pgs_track(**properties):
    return {
        'id': 0,
        'type': 'subtitles',
        'codec': 'HDMV PGS',
        'properties': {
            'default_track': False,
            'enabled_track': True,
            'forced_track': False,
            'language': 'eng',
            'language_ietf': 'en',
            **properties,
        },
    }


def test_flags_builds_a_track_flags_from_container_and_guessed_attributes():
    track = MkvTrack(_pgs_track(flag_hearing_impaired=True, flag_commentary=True, track_name='English'))

    assert track.flags == TrackFlags(hearing_impaired=True, commentary=True)


def test_flags_prefers_the_container_flag_over_a_conflicting_name_guess():
    track = MkvTrack(_pgs_track(forced_track=False, track_name='Forced'))

    assert track.flags == TrackFlags(forced=True)


def test_flags_is_empty_when_nothing_is_set():
    track = MkvTrack(_pgs_track(track_name='English'))

    assert track.flags == TrackFlags()
