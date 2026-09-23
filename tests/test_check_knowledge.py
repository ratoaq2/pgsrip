import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'check_knowledge.py'


@pytest.fixture(scope='module')
def ck() -> ModuleType:
    spec = importlib.util.spec_from_file_location('check_knowledge', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ('pattern', 'path', 'expected'),
    [
        ('pgsrip/ripper.py', 'pgsrip/ripper.py', True),
        ('pgsrip/*.py', 'pgsrip/ripper.py', True),
        ('pgsrip/*.py', 'pgsrip/sub/ripper.py', False),
        ('pgsrip/**', 'pgsrip/sub/ripper.py', True),
        ('**/*.md', 'README.md', True),
        ('**/*.md', 'docs/rip-e2e.md', True),
        ('tests/test_rip_e2e.*', 'tests/test_rip_e2e.yml', True),
        ('tests/test_rip_e2e.*', 'tests/test_rip_e2exyml', False),
    ],
)
def test_glob_to_regex(ck: ModuleType, pattern: str, path: str, expected: bool) -> None:
    assert bool(ck.glob_to_regex(pattern).match(path)) is expected


def test_rule_paths(ck: ModuleType) -> None:
    text = '---\r\npaths:\r\n  - "pgsrip/pgs.py"\r\n  - tests/**\r\n---\r\n\r\n# Title\r\n'
    assert ck.rule_paths(text) == ['pgsrip/pgs.py', 'tests/**']
    assert ck.rule_paths('# No frontmatter\n') == []


def test_path_references(ck: ModuleType) -> None:
    text = (
        'See `docs/a.md` and `pgsrip/`, not `ripper.py`, `plans/<item>/`, `tests/*.py` or `uv run pytest`.\n'
        '```\n`docs/in_fence.md`\n```\n'
    )
    assert ck.path_references(text, ('docs/', 'pgsrip/', 'tests/')) == ['docs/a.md', 'pgsrip/']


def test_top_level_dirs(ck: ModuleType) -> None:
    assert ck.top_level_dirs(['README.md', 'docs/a.md', 'pgsrip/sub/x.py', '.claude/rules/r.md']) == (
        '.claude/',
        'docs/',
        'pgsrip/',
    )


def test_check_finds_broken_references(ck: ModuleType, tmp_path: Path) -> None:
    files = {
        'CLAUDE.md': 'See `docs/a.md` and `docs/missing.md`.',
        'docs/a.md': 'Code in `pgsrip/`.',
        'pgsrip/core.py': '',
        '.claude/rules/r.md': '---\npaths:\n  - "pgsrip/*.py"\n  - "pgsrip/gone.py"\n---\n',
    }
    for name, content in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(content, encoding='utf-8')

    assert ck.check(tmp_path, list(files)) == [
        '.claude/rules/r.md: paths glob `pgsrip/gone.py` matches no file',
        'CLAUDE.md: `docs/missing.md` does not exist',
    ]


def test_covering_rules(ck: ModuleType, tmp_path: Path) -> None:
    rule = '.claude/rules/r.md'
    (tmp_path / rule).parent.mkdir(parents=True)
    (tmp_path / rule).write_text('---\npaths:\n  - "pgsrip/pgs.py"\n---\n', encoding='utf-8')

    assert ck.covering_rules(tmp_path, [rule], ['pgsrip/pgs.py', 'README.md']) == {rule: ['pgsrip/pgs.py']}
    assert ck.covering_rules(tmp_path, [rule], ['README.md']) == {}


def test_repository_knowledge_is_consistent(ck: ModuleType) -> None:
    assert ck.check(ck.ROOT, ck.repo_files()) == []
