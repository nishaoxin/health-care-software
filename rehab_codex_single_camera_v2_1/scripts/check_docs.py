"""Check relative Markdown links in the project's publishable files."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r'!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+["\'][^"\']*["\'])?\)')


def main():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    files = sorted({ROOT/name for name in names.decode('utf-8').split('\0') if name.endswith('.md')})
    errors = []
    checked = 0
    for path in files:
        if not path.is_file():
            continue
        fenced = False
        for lineno, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if line.lstrip().startswith(('```', '~~~')):
                fenced = not fenced
                continue
            if fenced:
                continue
            for match in LINK.finditer(line):
                value = match[1].strip('<>')
                parsed = urlsplit(value)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                relative = unquote(parsed.path)
                target = ((ROOT/relative.lstrip('/')) if relative.startswith('/') else (path.parent/relative)).resolve()
                checked += 1
                if not target.is_relative_to(ROOT) or not target.exists():
                    errors.append(f'{path.relative_to(ROOT).as_posix()}:{lineno}: {value}')
    for error in errors:
        print(error)
    print(f'{checked} relative links checked; {len(errors)} invalid.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
