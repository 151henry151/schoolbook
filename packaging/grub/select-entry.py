#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Keep one complete native GRUB entry; preserve its boot commands and header helpers."""
import argparse
import json
import re
import subprocess
from pathlib import Path


def select_entry(text: str, entry_id: str, label: str, css_class: str) -> str:
    lines = text.splitlines(keepends=True)
    # Native Debian generators put top-level entries and closing braces in column 0.
    first = next((i for i, line in enumerate(lines) if line.startswith(('menuentry ', 'submenu '))), None)
    starts = [i for i, line in enumerate(lines) if line.startswith('menuentry ')
              and re.search(r"['\"]" + re.escape(entry_id) + r"['\"]", line)]
    if first is None or len(starts) != 1:
        raise ValueError(f'Expected exactly one native boot entry {entry_id!r}')
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == '}'
                and lines[i].startswith('}')), None)
    if end is None:
        raise ValueError('Unterminated native boot entry')
    body = ''.join(lines[start + 1:end])
    if not re.search(r'^\s*linux\s+', body, re.M) or not re.search(r'^\s*initrd\s+', body, re.M):
        raise ValueError('Boot entry must retain both a kernel and initrd')
    if re.search(r'^\s*(menuentry|submenu)\s+', body, re.M):
        raise ValueError('Unexpected nested menu')
    return (''.join(lines[:first]) + f"menuentry '{label}' --class {css_class} --id {css_class} {{\n"
            + body + '}\n')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=('schoolbook', 'computer'))
    args = parser.parse_args()
    config = json.loads(Path('/etc/schoolbook-boot.json').read_text())
    generator = '10_linux' if args.kind == 'schoolbook' else '30_os-prober'
    text = subprocess.check_output(['/bin/sh', f'/usr/lib/schoolbook-boot/{generator}.distrib'], text=True)
    label = 'Schoolbook' if args.kind == 'schoolbook' else 'Computer'
    print(select_entry(text, config[args.kind], label, args.kind), end='')


if __name__ == '__main__':
    main()
