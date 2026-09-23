"""Check the AI knowledge files against the repository.

Without arguments, it fails when:
- a glob in the ``paths:`` frontmatter of a ``.claude/rules/*.md`` file matches no tracked file,
- a knowledge file names, in backticks, a repository path that does not exist.

With ``--changed [BASE]``, it lists the rules (and the docs they link to) that cover the files changed since
BASE (default: ``main``). Read them and fix every statement that the change makes wrong.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = '.claude/rules'
KNOWLEDGE_GLOBS = ('CLAUDE.md', 'CONTRIBUTING.md', 'docs/**/*.md', '.claude/**/*.md')
CHECKED_PREFIXES = ('pgsrip/', 'tests/', 'docs/', 'scripts/', '.claude/', '.github/')
PLACEHOLDER_CHARS = frozenset('<>*{}[]|$')

FENCED_BLOCK = re.compile(r'^```.*?^```', re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r'`([^`\s]+)`')
FRONTMATTER = re.compile(r'\A---\n(.*?)\n---\n', re.DOTALL)
FRONTMATTER_ITEM = re.compile(r'^\s*-\s*["\']?([^"\'\n]+?)["\']?\s*$', re.MULTILINE)


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a gitignore-like glob (``*``, ``?``, ``**``) to a regex over repo-relative posix paths."""
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith('**/', i):
            parts.append('(?:.*/)?')
            i += 3
        elif pattern.startswith('**', i):
            parts.append('.*')
            i += 2
        elif pattern[i] == '*':
            parts.append('[^/]*')
            i += 1
        elif pattern[i] == '?':
            parts.append('[^/]')
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile(''.join(parts) + r'\Z')


def matches(pattern: str, files: Iterable[str]) -> list[str]:
    regex = glob_to_regex(pattern)
    return [f for f in files if regex.match(f)]


def rule_paths(text: str) -> list[str]:
    """Return the globs of the ``paths:`` frontmatter list."""
    frontmatter = FRONTMATTER.match(text.replace('\r\n', '\n'))
    if not frontmatter:
        return []
    _, _, after = frontmatter.group(1).partition('paths:')
    return FRONTMATTER_ITEM.findall(after)


def path_references(text: str) -> list[str]:
    """Return the repository paths that the text names in inline code."""
    text = FENCED_BLOCK.sub('', text.replace('\r\n', '\n'))
    return [
        ref
        for ref in INLINE_CODE.findall(text)
        if ref.startswith(CHECKED_PREFIXES) and not PLACEHOLDER_CHARS.intersection(ref)
    ]


def exists(ref: str, files: Sequence[str]) -> bool:
    ref = ref.rstrip('/')
    return any(f == ref or f.startswith(ref + '/') for f in files)


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in result.stdout.splitlines() if line]


def repo_files() -> list[str]:
    """Tracked files plus new files that are not ignored, so a check before the first commit works."""
    return git_lines('ls-files', '--cached', '--others', '--exclude-standard')


def knowledge_files(files: Sequence[str]) -> list[str]:
    return sorted({f for pattern in KNOWLEDGE_GLOBS for f in matches(pattern, files)})


def check(root: Path, files: Sequence[str]) -> list[str]:
    errors: list[str] = []
    present = [f for f in files if (root / f).exists()]
    for rule in matches(f'{RULES_DIR}/*.md', present):
        for pattern in rule_paths((root / rule).read_text(encoding='utf-8')):
            if not matches(pattern, present):
                errors.append(f'{rule}: paths glob `{pattern}` matches no file')
    for doc in knowledge_files(present):
        for ref in path_references((root / doc).read_text(encoding='utf-8')):
            if not exists(ref, present):
                errors.append(f'{doc}: `{ref}` does not exist')
    return errors


def covering_rules(root: Path, files: Sequence[str], changed: Sequence[str]) -> dict[str, list[str]]:
    """Map each rule that covers a changed file to the changed files it covers."""
    result: dict[str, list[str]] = {}
    for rule in matches(f'{RULES_DIR}/*.md', files):
        covered = sorted(
            {f for pattern in rule_paths((root / rule).read_text(encoding='utf-8')) for f in matches(pattern, changed)}
        )
        if covered:
            result[rule] = covered
    return result


def report_changed(base: str) -> None:
    merge_base = git_lines('merge-base', base, 'HEAD')[0]
    changed = sorted(
        set(git_lines('diff', '--name-only', merge_base)) | set(git_lines('ls-files', '--others', '--exclude-standard'))
    )
    files = repo_files()
    rules = covering_rules(ROOT, files, changed)
    if not rules:
        print(f'No rule covers the {len(changed)} changed files. Check CLAUDE.md and CONTRIBUTING.md only.')
        return
    for rule, covered in rules.items():
        docs = [ref for ref in path_references((ROOT / rule).read_text(encoding='utf-8')) if ref.startswith('docs/')]
        print(rule)
        print(f'  covers: {", ".join(covered)}')
        if docs:
            print(f'  docs:   {", ".join(docs)}')


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--changed', nargs='?', const='main', metavar='BASE', help='list the rules to review')
    args = parser.parse_args(argv)
    if args.changed:
        report_changed(args.changed)
        return 0
    errors = check(ROOT, repo_files())
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
