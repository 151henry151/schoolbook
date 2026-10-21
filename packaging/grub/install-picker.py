#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Install a two-entry BIOS GRUB picker without rebooting or reinstalling the bootloader."""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('select_entry', ROOT / 'select-entry.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run(*args):
    return subprocess.run(args, check=True, text=True)


def install(schoolbook_id: str, computer_id: str) -> None:
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the target laptop.')
    if Path('/sys/firmware/efi').exists():
        raise SystemExit('This installer is for the inspected BIOS GRUB setup only.')
    helper = Path('/usr/lib/schoolbook-boot')
    theme = Path('/boot/grub/themes/schoolbook')
    dropin = Path('/etc/default/grub.d/99-schoolbook-picker.cfg')
    footer = Path('/etc/grub.d/99_schoolbook_wait')
    state = Path('/etc/schoolbook-boot.json')
    for path in (helper, theme, dropin, footer, state):
        if path.exists():
            raise SystemExit(f'{path} already exists; restore the previous installation before reinstalling.')
    cfg = Path('/boot/grub/grub.cfg')
    native = cfg.read_text()
    for kind, entry_id in [('schoolbook', schoolbook_id), ('computer', computer_id)]:
        module.select_entry(native, entry_id, kind.title(), kind)
    for name in ('10_linux', '30_os-prober'):
        path = '/etc/grub.d/' + name
        if subprocess.check_output(['dpkg-divert', '--list', path], text=True).strip():
            raise SystemExit(f'{path} is already diverted; refusing to overwrite its configuration.')
    backup = Path('/var/backups') / ('schoolbook-boot-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700)
    shutil.copytree('/etc/grub.d', backup / 'grub.d')
    shutil.copy2('/etc/default/grub', backup / 'grub-default')
    shutil.copy2(cfg, backup / 'grub.cfg')
    if Path('/etc/default/grub.d').exists():
        shutil.copytree('/etc/default/grub.d', backup / 'grub-default.d')
    diverted = []
    published = False
    try:
        helper.mkdir(mode=0o755)
        shutil.copy2(ROOT / 'select-entry.py', helper / 'select-entry.py')
        shutil.copytree(ROOT / 'picker', theme)
        for size, style, source in [(20, 'regular', 'DejaVuSans.ttf'), (30, 'heading', 'DejaVuSans-Bold.ttf'),
                                    (36, 'choice', 'DejaVuSans-Bold.ttf'),
                                    (16, 'terminal', 'DejaVuSansMono.ttf')]:
            run('grub-mkfont', '-r', '0x20-0x7e', '-s', str(size), '-o', str(theme / f'{style}.pf2'),
                '/usr/share/fonts/truetype/dejavu/' + source)
        state.write_text(json.dumps(
            {'schoolbook': schoolbook_id, 'computer': computer_id}, indent=2)+'\n')
        state.chmod(0o644)
        for name, kind in [('10_linux', 'schoolbook'), ('30_os-prober', 'computer')]:
            path = Path('/etc/grub.d') / name
            run('dpkg-divert', '--local', '--rename', '--divert', str(helper / (name + '.distrib')),
                '--add', str(path))
            diverted.append(name)
            path.write_text('#!/bin/sh\nexec /usr/bin/python3 '
                            '/usr/lib/schoolbook-boot/select-entry.py '+kind+'\n')
            path.chmod(0o755)
        dropin.parent.mkdir(exist_ok=True)
        dropin.write_text('''# Schoolbook/Computer picker; installed by packaging/grub/install-picker.py
GRUB_DEFAULT=schoolbook
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMEOUT=-1
GRUB_RECORDFAIL_TIMEOUT=-1
GRUB_DISABLE_OS_PROBER=false
GRUB_TERMINAL_OUTPUT=gfxterm
GRUB_GFXMODE=1024x768,auto
GRUB_THEME=/boot/grub/themes/schoolbook/theme.txt
''')
        dropin.chmod(0o644)
        # Last generator wins even after recordfail or os-prober timeout adjustments.
        footer.write_text("#!/bin/sh\ncat <<'EOF'\nset default=schoolbook\n"
                          "set timeout_style=menu\nset timeout=-1\nEOF\n")
        footer.chmod(0o755)
        candidate = Path('/boot/grub/grub.cfg.schoolbook-new')
        run('grub-mkconfig', '-o', str(candidate))
        run('grub-script-check', str(candidate))
        result = candidate.read_text()
        entries = re.findall(r"^menuentry '([^']+)'", result, re.M)
        all_entries = re.findall(r"^\s*menuentry '([^']+)'", result, re.M)
        # Debian emits a firmware entry guarded by grub_platform=efi, even on BIOS.
        # It is unreachable on this inspected BIOS machine and need not be diverted.
        firmware_only = (all_entries == entries + ['UEFI Firmware Settings']
                         and 'if [ "$grub_platform" = "efi" ]; then' in result)
        if (entries != ['Schoolbook', 'Computer'] or re.search(r'^\s*submenu ', result, re.M)
                or (all_entries != entries and not firmware_only)):
            raise RuntimeError(f'Expected only Schoolbook and Computer, got {entries!r}')
        for kind, entry_id in [('schoolbook', schoolbook_id), ('computer', computer_id)]:
            old = module.select_entry(native, entry_id, kind.title(), kind)
            # Kernel and initrd commands must still match the previously working entries.
            commands = re.findall(r'^\s*(?:linux|initrd)\s+.*$', old, re.M)
            if not all(command.strip() in result for command in commands):
                raise RuntimeError(f'{kind} boot commands changed unexpectedly; review before installing')
        os.replace(candidate, cfg)
        published = True
        restore = backup / 'restore.sh'
        restore.write_text(f'''#!/bin/sh
set -eu
# Restore the previous working menu without rebooting.
rm -f /etc/grub.d/10_linux /etc/grub.d/30_os-prober
for name in 10_linux 30_os-prober; do
  dpkg-divert --rename --divert /usr/lib/schoolbook-boot/$name.distrib --remove /etc/grub.d/$name
done
rm -f /etc/grub.d/99_schoolbook_wait /etc/default/grub.d/99-schoolbook-picker.cfg
rm -f /etc/schoolbook-boot.json
cp -a {backup}/grub.d/. /etc/grub.d/
cp -a {backup}/grub-default /etc/default/grub
cp -a {backup}/grub.cfg /boot/grub/grub.cfg.restore
mv /boot/grub/grub.cfg.restore /boot/grub/grub.cfg
rm -rf /usr/lib/schoolbook-boot /boot/grub/themes/schoolbook
printf 'Previous boot menu restored. No reboot performed.\\n'
''')
        restore.chmod(0o700)
        print('Installed two-choice picker; no restart performed. Backup and restore script:', backup)
    except BaseException:
        if published:
            shutil.copy2(backup / 'grub.cfg', cfg)
        for name in reversed(diverted):
            path = Path('/etc/grub.d') / name
            path.unlink(missing_ok=True)
            run('dpkg-divert', '--rename', '--divert', str(helper / (name + '.distrib')),
                '--remove', str(path))
        for path in (state, dropin, footer):
            path.unlink(missing_ok=True)
        shutil.rmtree(theme, ignore_errors=True)
        shutil.rmtree(helper, ignore_errors=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schoolbook-id', required=True, help='Existing native Trixie menuentry ID')
    parser.add_argument('--computer-id', required=True, help='Existing native Jessie menuentry ID')
    args = parser.parse_args()
    install(args.schoolbook_id, args.computer_id)
