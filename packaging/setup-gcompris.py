#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Install GCompris offline English assets/settings for the account running the kiosk.

Run after installing Debian's gcompris-qt package. No elevated permissions are
needed when run as the kiosk account. Existing activity progress is preserved.
"""

import configparser
import hashlib
import os
import re
import urllib.request
from pathlib import Path

BASE = 'https://cdn.kde.org/gcompris/data3/'


def fetch_assets(destination: Path, folder: str, prefixes: tuple[str, ...]) -> None:
    with urllib.request.urlopen(BASE + folder + 'Contents', timeout=30) as response:
        contents = response.read().decode('utf-8')
    target = destination / folder
    target.mkdir(parents=True, exist_ok=True)
    selected = []
    for prefix in prefixes:
        matches = [line.split() for line in contents.splitlines()
                   if len(line.split()) == 2 and line.split()[1].startswith(prefix)]
        if len(matches) != 1:
            raise ValueError(f'Expected one asset for {prefix}')
        digest, filename = matches[0]
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+\.rcc', filename):
            raise ValueError('Unexpected asset filename')
        path = target / filename
        if not path.exists() or hashlib.md5(path.read_bytes()).hexdigest() != digest:
            print(f'Downloading {filename}', flush=True)
            temporary = path.with_suffix('.part')
            checksum = hashlib.md5()
            with urllib.request.urlopen(BASE + folder + filename, timeout=60) as response:
                with temporary.open('wb') as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        checksum.update(chunk)
            if checksum.hexdigest() != digest:
                temporary.unlink()
                raise ValueError(f'Asset checksum mismatch: {filename}')
            temporary.replace(path)
        selected.append(f'{digest}  {filename}')
    # Retain entries for other installed locales if this setup is rerun.
    index = target / 'Contents'
    old = index.read_text().splitlines() if index.exists() else []
    retained = [line for line in old if len(line.split()) == 2
                and not any(line.split()[1].startswith(prefix) for prefix in prefixes)]
    index.write_text('\n'.join(retained + selected) + '\n')
    print(f'Verified {", ".join(prefixes)}', flush=True)


def main() -> None:
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    destination = data / 'gcompris-qt/data3'
    fetch_assets(destination, 'voices-ogg/', ('voices-en-', 'voices-en_US-'))
    fetch_assets(destination, 'words/', ('words-webp-',))
    fetch_assets(destination, 'backgroundMusic/', ('backgroundMusic-ogg-',))
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    path = config_home / 'gcompris/gcompris-qt.conf'
    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    if path.exists():
        settings.read(path)
        backup = path.with_suffix('.conf.before-schoolbook')
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    for section in ('%General', 'Admin'):
        if section not in settings:
            settings.add_section(section)
    settings['%General'].update({'locale': 'en_US.UTF-8', 'enableAudioVoices': 'true',
                                'enableAudioEffects': 'true', 'enableBackgroundMusic': 'false',
                                'virtualKeyboard': 'false', 'exitConfirmation': 'false',
                                'enableAutomaticDownloads': 'false'})
    settings['Admin']['renderer'] = 'software'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w') as output:
        settings.write(output, space_around_delimiters=False)
    print(f'English voices and offline resources ready: {destination}')


if __name__ == '__main__':
    main()
