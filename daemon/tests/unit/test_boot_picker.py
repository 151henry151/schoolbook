# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Check the generator preserves boot commands and never silently selects a wrong OS."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('boot_picker', Path('packaging/grub/select-entry.py'))
picker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(picker)

NATIVE = '''function gfxmode {
  set gfxpayload="${1}"
}
set linux_gfx_mode=
menuentry 'Debian' --class debian $menuentry_id_option 'gnulinux-simple-abc' {
  insmod lvm
  search --fs-uuid --set=root abc
  linux /boot/vmlinuz-new root=/dev/mapper/vg-schoolbook ro net.ifnames=0
  initrd /boot/initrd.img-new
}
submenu 'Advanced' {
  menuentry 'Recovery' {
    linux /boot/vmlinuz-old single
    initrd /boot/initrd.img-old
  }
}
menuentry 'DebianEdu/Skolelinux' $menuentry_id_option 'osprober-gnulinux-simple-def' {
  search --fs-uuid --set=root boot-uuid
  linux /vmlinuz-jessie root=/dev/mapper/vg-root ro quiet
  initrd /initrd.img-jessie
}
'''


def test_schoolbook_uses_current_kernel_and_preserves_helpers():
    text = picker.select_entry(NATIVE, 'gnulinux-simple-abc', 'Schoolbook', 'schoolbook')
    assert "menuentry 'Schoolbook' --class schoolbook --id schoolbook" in text
    assert 'function gfxmode' in text
    assert 'linux /boot/vmlinuz-new root=/dev/mapper/vg-schoolbook ro net.ifnames=0' in text
    assert 'initrd /boot/initrd.img-new' in text
    assert 'Recovery' not in text and 'submenu' not in text and 'Skolelinux' not in text
    updated = picker.select_entry(NATIVE.replace('vmlinuz-new', 'vmlinuz-next'),
                                  'gnulinux-simple-abc', 'Schoolbook', 'schoolbook')
    assert 'vmlinuz-next' in updated


def test_computer_preserves_separate_jessie_boot_partition():
    text = picker.select_entry(NATIVE, 'osprober-gnulinux-simple-def', 'Computer', 'computer')
    assert "menuentry 'Computer' --class computer --id computer" in text
    assert 'search --fs-uuid --set=root boot-uuid' in text
    assert 'linux /vmlinuz-jessie root=/dev/mapper/vg-root ro quiet' in text
    assert 'initrd /initrd.img-jessie' in text
    assert 'vmlinuz-new' not in text and 'submenu' not in text


@pytest.mark.parametrize('text,entry_id', [
    (NATIVE, 'nonexistent'),
    (NATIVE.replace('  initrd /boot/initrd.img-new\n', ''), 'gnulinux-simple-abc'),
    (NATIVE + NATIVE, 'gnulinux-simple-abc'),
    ("menuentry 'broken' --id 'broken' {\n linux /vmlinuz\n initrd /initrd\n", 'broken'),
])
def test_missing_duplicate_or_broken_entries_fail_closed(text, entry_id):
    with pytest.raises(ValueError):
        picker.select_entry(text, entry_id, 'Schoolbook', 'schoolbook')
