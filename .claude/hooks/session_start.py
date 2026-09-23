"""SessionStart hook: show the local work item of the current branch.

A branch like ``fix/135-pts-zero`` maps to ``plans/135-*/``. The hook prints the item's ``README.md`` so the
new session knows the stage and the next step. It prints nothing when there is no match.
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MAX_LINES = 40


def main() -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding='utf-8')
    result = subprocess.run(['git', 'branch', '--show-current'], cwd=ROOT, capture_output=True, text=True)
    issue = re.search(r'/(\d+)-', result.stdout.strip())
    if not issue:
        return
    for readme in sorted((ROOT / 'plans').glob(f'{issue.group(1)}-*/README.md')):
        lines = readme.read_text(encoding='utf-8').splitlines()[:MAX_LINES]
        print(f'Work item for this branch: {readme.parent.relative_to(ROOT).as_posix()}/ (see docs/workflow.md)')
        print('\n'.join(lines))


if __name__ == '__main__':
    main()
