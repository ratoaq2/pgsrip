# -*- coding: utf-8 -*-
import re
from datetime import timedelta
from typing import List, Tuple, Optional

import click
import logging
import os

from babelfish import Error as BabelfishError, Language

from pgsrip import api
from pgsrip.media import Media
from pgsrip.options import Options

logger = logging.getLogger('pgsrip')


class LanguageParamType(click.ParamType):
    name = 'language'

    def convert(self, value, param, ctx):
        try:
            return Language.fromietf(value)
        except (BabelfishError, ValueError):
            self.fail(f"{click.style(f'{value}', bold=True)} is not a valid language")


class AgeParamType(click.ParamType):
    name = 'age'

    def convert(self, value, param, ctx):
        match = re.match(r'^(?:(?P<weeks>\d+?)w)?(?:(?P<days>\d+?)d)?(?:(?P<hours>\d+?)h)?$', value)
        if not match:
            self.fail('%s is not a valid age' % value)

        return timedelta(**{k: int(v) for k, v in match.groupdict('0').items()})


LANGUAGE = LanguageParamType()
AGE = AgeParamType()


@click.command()
@click.option('-c', '--config', type=click.Path(), help='cleanit configuration path to be used')
@click.option('-l', '--language', type=LANGUAGE, multiple=True, help='Language as IETF code, '
              'e.g. en, pt-BR (can be used multiple times).')
@click.option('-t', '--tag', required=False, multiple=True, help='Rule tags to be used, '
              'e.g. ocr, tidy, no-sdh, no-style, no-lyrics, no-spam (can be used multiple times). ')
@click.option('-e', '--encoding', help='Save subtitles using the following encoding.')
@click.option('-a', '--age', type=AGE, help='Filter videos newer than AGE, e.g. 12h, 1w2d.')
@click.option('-A', '--srt-age', type=AGE, help='Filter videos which srt subtitles are newer than AGE, e.g. 12h, 1w2d.')
@click.option('-f', '--force', is_flag=True, default=False,
              help='re-rip and overwrite existing srt subtitles, even if they already exist')
@click.option('-a', '--all', is_flag=True, default=False,
              help='rip all tracks for a given language, even another track for that language was already ripped')
@click.option('-w', '--max-workers', type=click.IntRange(1, 50), default=None, help='Maximum number of threads to use.')
@click.option('--debug', is_flag=True, help='Print useful information for debugging and for reporting bugs.')
@click.option('-v', '--verbose', count=True, help='Display debug messages')
@click.argument('path', type=click.Path(), required=True, nargs=-1)
def pgsrip(config: Optional[str], language: Optional[Tuple[Language]], tag: Tuple[str], encoding: Optional[str],
           age: timedelta, srt_age: timedelta, force: bool, all: bool, debug: bool, max_workers: Optional[int],
           verbose: int, path: Tuple[str]):
    if debug:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    if config and (not os.path.isfile(config) or os.path.isdir(config)):
        click.echo(f"Invalid configuration is defined: {click.style(config, bold=True)}")
        return

    options = Options(config_path=config, languages=set(language), tags=set(tag), encoding=encoding,
                      overwrite=force, one_per_lang=not all, max_workers=max_workers, age=age, srt_age=srt_age)

    rules = options.config.select_rules(tags=options.tags, languages=options.languages)
    if not rules:
        click.echo(f"No rules defined for "
                   f"{click.style(', '.join(tag + tuple(str(lang) for lang in options.languages)), bold=True)}")
        return

    collected_medias: List[Media] = []
    filtered_out_paths: List[str] = []
    discarded_paths: List[str] = []
    for p in path:
        c, f, d = api.scan_path(p, options)
        collected_medias.extend(c)
        filtered_out_paths.extend(f)
        discarded_paths.extend(d)

    if debug or verbose > 1:
        if verbose > 2:
            for p in filtered_out_paths:
                click.echo(f"{click.style(p, fg='yellow', bold=True)} filtered out")
        for p in discarded_paths:
            click.echo(f"{click.style(p, fg='red', bold=True)} discarded")

    collected_pgs_medias = []
    if debug or verbose > 1:
        for m in collected_medias:
            collected_pgs_medias.extend(list(m.get_pgs_medias(options)))
    else:
        with click.progressbar(collected_medias,
                               label='Collecting pgs subtitles', item_show_func=lambda item: str(item or '')) as bar:
            for m in bar:
                collected_pgs_medias.extend(list(m.get_pgs_medias(options)))

    # report collected medias
    report = (f"{click.style(str(len(collected_pgs_medias)), bold=True, fg='green')} "
              f"PGS subtitle{'s' if len(collected_pgs_medias) > 1 else ''} collected "
              f"from {click.style(str(len(collected_medias)), bold=True, fg='green')} "
              f"file{'s' if len(collected_medias) > 1 else ''}")
    if filtered_out_paths:
        report += (f" / {click.style(str(len(filtered_out_paths)), bold=True, fg='yellow')} "
                   f"file{'s' if len(filtered_out_paths) > 1 else ''} filtered out")
    if discarded_paths:
        report += (f" / {click.style(str(len(discarded_paths)), bold=True, fg='red')} "
                   f"path{'s' if len(discarded_paths) > 1 else ''} ignored")
    click.echo(report)

    if debug or verbose > 1:
        for pgs in collected_pgs_medias:
            api.rip_pgs(pgs, options)
    else:
        ripped_count = 0
        with click.progressbar(collected_pgs_medias, label='Ripping subtitles', update_min_steps=0,
                               item_show_func=lambda s: click.style(str(s or ''), bold=True)) as bar:
            bar.short_limit = 0
            for pgs in bar:
                bar.update(0, pgs)
                ripped_count += api.rip_pgs(pgs, options)

        # report ripped subtitles
        click.echo(f"{click.style(str(ripped_count), bold=True, fg='green')} "
                   f"PGS subtitle{'s' if ripped_count > 1 else ''} ripped from "
                   f"{click.style(str(len(collected_medias)), bold=True, fg='blue')} "
                   f"file{'s' if len(collected_medias) > 1 else ''}")

