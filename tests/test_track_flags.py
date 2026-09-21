import itertools

import pytest

from pgsrip.track_flags import TrackFlags

FLAG_FIELDS = ('forced', 'hearing_impaired', 'closed_caption', 'commentary', 'descriptive')


def test_tokens_are_emitted_in_canonical_order():
    flags = TrackFlags(
        descriptive=True, commentary=True, closed_caption=True, hearing_impaired=True, forced=True, version='alternate'
    )

    assert flags.tokens() == ('forced', 'sdh', 'cc', 'commentary', 'descriptive', 'alternate')


def test_tokens_omits_unset_flags():
    assert TrackFlags(hearing_impaired=True).tokens() == ('sdh',)
    assert TrackFlags().tokens() == ()


def test_tokens_does_not_render_default_or_original():
    flags = TrackFlags(default=True, original=True)

    assert flags.tokens() == ()


FLAG_COMBINATIONS = [
    dict(zip(FLAG_FIELDS, values, strict=True)) for values in itertools.product([False, True], repeat=len(FLAG_FIELDS))
]


@pytest.mark.parametrize('combination', FLAG_COMBINATIONS)
@pytest.mark.parametrize('version', [None, 'alternate'])
def test_parse_round_trips_every_combination(combination, version):
    flags = TrackFlags(version=version, **combination)

    parsed, remaining = TrackFlags.parse(list(flags.tokens()))

    assert parsed == TrackFlags(**combination, version=version)
    assert remaining == []


def test_parse_stops_at_the_first_unrecognised_token():
    parsed, remaining = TrackFlags.parse(['movie', 'en', 'sdh', 'forced'])

    assert parsed == TrackFlags(forced=True, hearing_impaired=True)
    assert remaining == ['movie', 'en']


def test_parse_returns_defaults_and_all_tokens_back_when_nothing_matches():
    parsed, remaining = TrackFlags.parse(['movie', 'en'])

    assert parsed == TrackFlags()
    assert remaining == ['movie', 'en']


@pytest.mark.parametrize('alias, field', [('hi', 'hearing_impaired'), ('foreign', 'forced')])
def test_parse_accepts_aliases_that_are_never_emitted(alias, field):
    parsed, remaining = TrackFlags.parse(['movie', 'en', alias])

    assert getattr(parsed, field) is True
    assert remaining == ['movie', 'en']
    assert alias not in parsed.tokens()


def test_matches_with_empty_include_and_exclude_allows_everything():
    assert TrackFlags().matches(include=frozenset(), exclude=frozenset())
    assert TrackFlags(forced=True).matches(include=frozenset(), exclude=frozenset())


def test_matches_full_means_no_visible_flags():
    assert TrackFlags().matches(include=frozenset({'full'}), exclude=frozenset())
    assert not TrackFlags(forced=True).matches(include=frozenset({'full'}), exclude=frozenset())


def test_matches_include_requires_at_least_one_listed_flag():
    flags = TrackFlags(hearing_impaired=True)

    assert flags.matches(include=frozenset({'sdh'}), exclude=frozenset())
    assert not flags.matches(include=frozenset({'forced'}), exclude=frozenset())


def test_matches_exclude_wins_over_include():
    flags = TrackFlags(forced=True)

    assert not flags.matches(include=frozenset({'forced'}), exclude=frozenset({'forced'}))


def test_matches_default_and_original_and_alternate_tokens():
    assert TrackFlags(default=True).matches(include=frozenset({'default'}), exclude=frozenset())
    assert TrackFlags(original=True).matches(include=frozenset({'original'}), exclude=frozenset())
    assert TrackFlags(version='alternate').matches(include=frozenset({'alternate'}), exclude=frozenset())


def test_track_flags_is_usable_as_a_dict_key():
    mapping = {TrackFlags(): 'full', TrackFlags(forced=True): 'forced'}

    assert mapping[TrackFlags()] == 'full'
    assert mapping[TrackFlags(forced=True)] == 'forced'
