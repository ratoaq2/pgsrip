import json
import os
import shutil
import tempfile
from subprocess import CalledProcessError

import pytest
from babelfish import Language

from pgsrip.api import pending, prepare, rip, scan
from pgsrip.engines.base import OcrEngine, Reading
from pgsrip.formats.pgs import CorruptDataError
from pgsrip.media import Media, Workspace
from pgsrip.options import Options
from pgsrip.sources.base import SourceError
from pgsrip.writers.srt import SrtWriter

from .fabricate import SAMPLE, FakeMkvToolNix, MediaSpec, TrackSpec, fabricate_fake, payload


@pytest.fixture
def mkvmerge(monkeypatch):
    def use(tracks=(), error=None):
        def check_output(cmd, *args, **kwargs):
            if error:
                raise error
            return json.dumps({'tracks': list(tracks)}).encode()

        monkeypatch.setattr('pgsrip.sources.mkvtoolnix.check_output', check_output)

    return use


@pytest.fixture
def mkvextract(tmp_path, monkeypatch):
    """Fabricate `movie.mkv` with 3 PGS tracks (en, de, fr). Return its path and the list of mkvextract calls."""
    temp_dir = tmp_path / 'temp'
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(temp_dir))

    def use(error=None):
        toolnix = FakeMkvToolNix()
        spec = MediaSpec(tracks=(TrackSpec(language='en'), TrackSpec(language='de'), TrackSpec(language='fr')))
        fabricate_fake(str(tmp_path), [spec], toolnix, monkeypatch)
        calls = []

        def check_output(cmd, *args, **kwargs):
            if cmd[0] == 'mkvextract':
                calls.append(cmd)
                if error:
                    raise error
            return toolnix.check_output(cmd, *args, **kwargs)

        monkeypatch.setattr('pgsrip.sources.mkvtoolnix.check_output', check_output)
        return os.path.join(str(tmp_path), spec.name), calls

    return use


def pgs_track(track_id=0, language='eng', **properties):
    return {
        'id': track_id,
        'type': 'subtitles',
        'codec': 'HDMV PGS',
        'properties': {'language': language, 'enabled_track': True, **properties},
    }


def create_file(directory, name):
    path = os.path.join(str(directory), name)
    with open(path, 'wb') as f:
        f.write(b'')

    return path


def test_scan_discards_non_existent_path():
    collected, filtered_out, discarded = scan('/no/such/media.mkv')

    assert not collected
    assert not filtered_out
    assert discarded[0].reason == 'path does not exist'


def test_scan_discards_unsupported_extension(tmp_path):
    path = create_file(tmp_path, 'mymedia.mp4')

    collected, _, discarded = scan(path)

    assert not collected
    assert [p.path for p in discarded] == [path]
    assert discarded[0].reason == 'unsupported extension, expected one of .mks, .mkv, .sup'


def test_scan_discards_when_mkvmerge_is_missing(tmp_path, mkvmerge):
    mkvmerge(error=FileNotFoundError('mkvmerge'))
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, _, discarded = scan(path)

    assert not collected
    assert discarded[0].reason == 'mkvmerge not found. Install MKVToolNix: https://mkvtoolnix.download/downloads.html'


def test_scan_discards_when_mkvmerge_fails(tmp_path, mkvmerge):
    mkvmerge(error=CalledProcessError(2, ['mkvmerge', '-i', '-F', 'json']))
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, _, discarded = scan(path)

    assert not collected
    assert discarded[0].reason == 'mkvmerge could not read the file (exit code 2)'


@pytest.mark.parametrize(
    'name, error',
    [
        ('mymedia.mp4', 'unsupported extension, expected one of .mks, .mkv, .sup'),
        ('mymedia.mkv', 'mkvmerge not found. Install MKVToolNix: https://mkvtoolnix.download/downloads.html'),
    ],
)
def test_media_raises_a_source_error_when_no_source_can_read_the_file(tmp_path, mkvmerge, name, error):
    mkvmerge(error=FileNotFoundError('mkvmerge'))
    path = create_file(tmp_path, name)

    with pytest.raises(SourceError) as raised:
        Media(path)

    assert str(raised.value) == error


def test_scan_collects_a_sup_with_no_tool(tmp_path, mkvmerge):
    mkvmerge(error=FileNotFoundError('mkvmerge'))
    path = create_file(tmp_path, 'mymedia.en.sup')

    collected, filtered_out, discarded = scan(path)

    assert [str(m.path) for m in collected] == [path]
    assert not filtered_out
    assert not discarded


def test_sup_is_filtered_by_its_file_name_flags(tmp_path):
    path = create_file(tmp_path, 'movie.en.forced.sup')

    assert Media(path).subtitles(Options(without_flags=frozenset({'forced'}))) == []
    (subtitle,) = Media(path).subtitles(Options(with_flags=frozenset({'forced'})))
    with subtitle:
        assert str(subtitle.output_base) == path


def test_scan_filters_out_other_languages(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track(language='eng'), pgs_track(track_id=1, language='deu')])
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, filtered_out, discarded = scan(path, Options(languages={Language('fra')}))

    assert not collected
    assert not discarded
    assert filtered_out[0].reason == 'no track for the selected languages (available: de, en)'


def test_scan_collects_supported_media(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track()])
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, filtered_out, discarded = scan(path)

    assert [str(m.path) for m in collected] == [path]
    assert not filtered_out
    assert not discarded


def test_scan_walks_directories_without_discarding_other_files(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track()])
    create_file(tmp_path, 'mymedia.mkv')
    create_file(tmp_path, 'mymedia.nfo')

    collected, filtered_out, discarded = scan(str(tmp_path))

    assert len(collected) == 1
    assert not filtered_out
    assert not discarded


def test_rip_raises_the_error_it_failed_with(tmp_path):
    (subtitle,) = Media(create_file(tmp_path, 'mymedia.en.sup')).subtitles(Options())

    with pytest.raises(CorruptDataError, match='No subtitle image'):
        rip(subtitle, Options())


def test_a_subtitle_points_at_the_media_the_subtitle_came_from(tmp_path):
    path = create_file(tmp_path, 'mymedia.en.sup')

    (subtitle,) = Media(path).subtitles(Options())

    assert str(subtitle.source_path) == path


def test_an_mkv_track_with_no_language_is_ripped_as_und(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track(language='und', language_ietf='und')])
    path = create_file(tmp_path, 'movie.mkv')

    medias = Media(path).subtitles(Options())

    assert [os.path.basename(str(m.output_path(SrtWriter()))) for m in medias] == ['movie.srt']


def test_subtitles_disambiguates_only_a_real_language_and_flags_collision(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
            pgs_track(track_id=2, language='eng'),
            pgs_track(track_id=3, language='deu'),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options(all_tracks=True)))

    assert sorted(os.path.basename(str(m.output_path(SrtWriter()))) for m in medias) == sorted(
        ['movie.en.srt', 'movie.en.sdh.srt', 'movie.en.track2.srt', 'movie.de.srt']
    )


def test_a_second_run_does_not_rip_the_duplicate_of_a_ripped_track(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track(track_id=0, language='eng'), pgs_track(track_id=2, language='eng')])
    path = create_file(tmp_path, 'movie.mkv')
    create_file(tmp_path, 'movie.en.srt')

    medias = pending(Media(path).subtitles(Options()), Options())

    assert [os.path.basename(str(m.output_path(SrtWriter()))) for m in medias] == []


@pytest.mark.parametrize(
    'options, names',
    [
        (Options(), ['movie.en.srt']),
        (Options(all_tracks=True), ['movie.en.srt', 'movie.en.track2.srt']),
    ],
)
def test_2_tracks_that_differ_only_in_the_default_flag_do_not_write_the_same_file(tmp_path, mkvmerge, options, names):
    mkvmerge(tracks=[pgs_track(track_id=0, language='eng'), pgs_track(track_id=1, language='eng', default_track=True)])
    path = create_file(tmp_path, 'movie.mkv')

    subtitles = Media(path).subtitles(options)

    assert [os.path.basename(str(s.output_path(SrtWriter()))) for s in subtitles] == names


def test_subtitles_keeps_different_flag_combinations_for_the_same_language_by_default(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options()))

    assert sorted(os.path.basename(str(m.output_path(SrtWriter()))) for m in medias) == [
        'movie.en.sdh.srt',
        'movie.en.srt',
    ]


def test_subtitles_track_id_is_stable_regardless_of_one_per_lang(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=2, language='eng'),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options()))

    assert [os.path.basename(str(m.output_path(SrtWriter()))) for m in medias] == ['movie.en.srt']


def test_subtitles_excludes_flagged_tracks(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_commentary=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options(all_tracks=True, without_flags=frozenset({'commentary'}))))

    assert [os.path.basename(str(m.output_path(SrtWriter()))) for m in medias] == ['movie.en.srt']


def test_subtitles_includes_forced_or_full_tracks(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng', forced_track=True),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
            pgs_track(track_id=2, language='eng'),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options(all_tracks=True, with_flags=frozenset({'forced', 'full'}))))

    assert sorted(os.path.basename(str(m.output_path(SrtWriter()))) for m in medias) == [
        'movie.en.forced.srt',
        'movie.en.srt',
    ]


def test_subtitles_includes_sdh_for_the_selected_language_only(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng', flag_hearing_impaired=True),
            pgs_track(track_id=1, language='eng'),
            pgs_track(track_id=2, language='deu', flag_hearing_impaired=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options(languages={Language('eng')}, with_flags=frozenset({'sdh'}))))

    assert [os.path.basename(str(m.output_path(SrtWriter()))) for m in medias] == ['movie.en.sdh.srt']


def test_subtitles_exclude_wins_over_include(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track(track_id=0, language='eng', forced_track=True, flag_commentary=True)])
    path = create_file(tmp_path, 'movie.mkv')

    medias = Media(path).subtitles(Options(with_flags=frozenset({'forced'}), without_flags=frozenset({'commentary'})))

    assert not medias


def test_subtitles_track_id_is_stable_regardless_of_with_without_filtering(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=2, language='eng'),
            pgs_track(track_id=5, language='eng', flag_commentary=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options(all_tracks=True, without_flags=frozenset({'commentary'}))))

    assert sorted(os.path.basename(str(m.output_path(SrtWriter()))) for m in medias) == [
        'movie.en.srt',
        'movie.en.track2.srt',
    ]


def test_subtitles_one_per_language_ignores_flags(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Media(path).subtitles(Options(one_per_language=True)))

    assert [os.path.basename(str(m.output_path(SrtWriter()))) for m in medias] == ['movie.en.srt']


def test_subtitles_extracts_all_tracks_with_one_call(mkvextract):
    path, calls = mkvextract()

    data = []
    with Workspace() as workspace:
        for subtitle in Media(path).subtitles(Options(all_tracks=True), workspace):
            with subtitle:
                data.append(subtitle.read())

    assert data == [payload()] * 3
    assert len(calls) == 1
    assert [target.partition(':')[0] for target in calls[0][3:]] == ['0', '1', '2']


def test_a_failed_extraction_fails_each_track(mkvextract):
    path, calls = mkvextract(error=CalledProcessError(2, ['mkvextract']))
    errors = []
    options = Options(all_tracks=True)

    with Workspace() as workspace:
        for subtitle in Media(path).subtitles(options, workspace):
            with pytest.raises(SourceError) as raised:
                rip(subtitle, options)
            errors.append(raised.value)

    assert [str(e) for e in errors] == ['mkvextract could not extract the tracks (exit code 2)'] * 3
    assert len(calls) == 1


def test_no_temp_dir_is_left_for_a_skipped_track(tmp_path, mkvextract):
    path, calls = mkvextract()
    create_file(tmp_path, 'movie.de.srt')
    create_file(tmp_path, 'movie.fr.srt')

    options = Options(all_tracks=True)
    with Workspace() as workspace:
        medias = pending(Media(path).subtitles(options, workspace), options)
        for subtitle in medias:
            with subtitle:
                subtitle.read()
        (run_dir,) = os.listdir(tempfile.tempdir)
        assert os.listdir(os.path.join(tempfile.tempdir, run_dir)) == []

    assert [str(subtitle.language) for subtitle in medias] == ['en']
    assert [target.partition(':')[0] for target in calls[0][3:]] == ['0']
    assert os.listdir(tempfile.tempdir) == []


def test_a_subtitle_with_no_pending_file_is_not_extracted_by_the_next_read(tmp_path, mkvextract):
    path, calls = mkvextract()
    create_file(tmp_path, 'movie.en.srt')

    options = Options(all_tracks=True)
    english, german, french = Media(path).subtitles(options)
    assert rip(english, options) is False
    for subtitle in (german, french):
        with subtitle:
            subtitle.read()

    assert [target.partition(':')[0] for target in calls[0][3:]] == ['1', '2']
    assert os.listdir(tempfile.tempdir) == []


def test_all_tracks_of_a_run_share_one_base_dir(mkvextract):
    path, _ = mkvextract()

    with Workspace(keep=True) as workspace:
        for subtitle in Media(path).subtitles(Options(all_tracks=True), workspace):
            with subtitle:
                subtitle.read()

    (base,) = os.listdir(tempfile.tempdir)
    assert base.startswith('pgsrip-')
    track_dirs = sorted(os.listdir(os.path.join(tempfile.tempdir, base)))
    assert [name.rpartition('-')[0] for name in track_dirs] == ['movie.de', 'movie.en', 'movie.fr']
    assert [os.listdir(os.path.join(tempfile.tempdir, base, name)) for name in track_dirs] == [
        ['1.de.sup'],
        ['0.en.sup'],
        ['2.fr.sup'],
    ]


def test_two_media_with_the_same_name_do_not_share_a_track_dir(tmp_path):
    with Workspace() as workspace:
        (first,) = Media(str(tmp_path / 'a' / 'movie.en.sup')).subtitles(Options(), workspace)
        (second,) = Media(str(tmp_path / 'b' / 'movie.en.sup')).subtitles(Options(), workspace)

        assert first.temp_dir != second.temp_dir
        assert os.path.dirname(first.temp_dir) == os.path.dirname(second.temp_dir) == workspace.dir


def test_a_subtitle_can_be_read_again_after_its_temp_dir_is_removed(mkvextract):
    path, calls = mkvextract()

    data = []
    with Workspace() as workspace:
        (subtitle,) = Media(path).subtitles(Options(languages=frozenset({Language('eng')})), workspace)
        for _ in range(2):
            with subtitle:
                data.append(subtitle.read())

    assert data == [payload()] * 2
    assert len(calls) == 2


def test_a_disabled_track_does_not_match_the_languages(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track(language='eng', enabled_track=False), pgs_track(track_id=1, language='deu')])
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, filtered_out, _ = scan(path, Options(languages=frozenset({Language('eng')})))

    assert not collected
    assert filtered_out[0].reason == 'no track for the selected languages (available: de)'


class PreparedEngine(OcrEngine):
    """Reads only the languages that it prepared."""

    def __init__(self, languages=None):
        self.languages = languages
        self.prepared = set()

    def prepare(self, languages, reporter=None):
        self.prepared.update(lang for lang in languages if self.languages is None or lang in self.languages)

    def supports(self, language):
        return language in self.prepared

    def recognize(self, items, language, debug_dir):
        return [Reading('text')] * len(items)


def test_rip_after_prepare_uses_an_engine_that_needs_prepare(tmp_path):
    path = str(tmp_path / 'movie.en.sup')
    shutil.copy(SAMPLE, path)
    options = Options(engines=[PreparedEngine()], post_processors=[])
    (subtitle,) = Media(path).subtitles(options)
    reported = []

    prepare([subtitle], options, reported.append)

    assert rip(subtitle, options)
    assert reported == []


def test_prepare_reports_a_language_that_an_engine_cannot_read(tmp_path):
    subtitles = [
        s for name in ('movie.en.sup', 'movie.de.sup') for s in Media(create_file(tmp_path, name)).subtitles(Options())
    ]
    reported = []

    prepare(subtitles, Options(engines=[PreparedEngine({Language('eng')})]), reported.append)

    assert reported == ['PreparedEngine cannot read de']
