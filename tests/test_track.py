import dataclasses

import pytest

from pgsrip.sources.mkvtoolnix import track_from_json
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
    actual = track_from_json(track)

    # then
    fields = {**vars(actual), **dataclasses.asdict(actual.flags)}
    del fields['flags']
    assert {k: v for k, v in fields.items() if v is not None and v is not False} == expected


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
    track = track_from_json(_pgs_track(flag_hearing_impaired=True, flag_commentary=True, track_name='English'))

    assert track.flags == TrackFlags(hearing_impaired=True, commentary=True)


def test_flags_prefers_the_container_flag_over_a_conflicting_name_guess():
    track = track_from_json(_pgs_track(forced_track=False, track_name='Forced'))

    assert track.flags == TrackFlags(forced=True)


def test_flags_is_empty_when_nothing_is_set():
    track = track_from_json(_pgs_track(track_name='English'))

    assert track.flags == TrackFlags()
