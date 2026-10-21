#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Build the original GRUB icons and nine-slice panels; requires Pillow only at build time."""
from pathlib import Path

from PIL import Image, ImageDraw

root = Path(__file__).parent / 'picker'
license_text = ('SPDX-License-Identifier: GPL-3.0-or-later\n'
                'SPDX-FileCopyrightText: 2026 Schoolbook contributors\n')

def save(image, path):
    image.save(path)
    path.with_suffix(path.suffix + '.license').write_text(license_text)

# GRUB 2.12 can emit a bitmap error on selection with only desktop-color.
save(Image.new('RGB', (8, 8), '#F4F0E8'), root / 'background.png')

for name, fill, border in [('option', '#FFFFFF', '#CAD5D5'), ('selected', '#176D80', '#0C5365')]:
    image = Image.new('RGBA', (49, 49))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 48, 48), radius=20, fill=fill, outline=border, width=3)
    for label, box in {'nw': (0, 0, 24, 24), 'n': (24, 0, 25, 24), 'ne': (25, 0, 49, 24),
                       'w': (0, 24, 24, 25), 'c': (24, 24, 25, 25), 'e': (25, 24, 49, 25),
                       'sw': (0, 25, 24, 49), 's': (24, 25, 25, 49), 'se': (25, 25, 49, 49)}.items():
        save(image.crop(box), root / f'{name}_{label}.png')
for name in ('schoolbook', 'computer'):
    image = Image.new('RGBA', (256, 256))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 254, 254), radius=52, fill='#F4C85B')
    if name == 'schoolbook':
        draw.polygon([(42, 64), (112, 73), (128, 86), (144, 73), (214, 64),
                      (214, 190), (144, 197), (128, 209), (112, 197), (42, 190)],
                     fill='#FFFFFF', outline='#183A46', width=10)
        draw.line((128, 86, 128, 204), fill='#183A46', width=8)
        for y in (103, 129, 155):
            draw.line((61, y, 107, y+6), fill='#78ACAD', width=7)
            draw.line((149, y+6, 195, y), fill='#78ACAD', width=7)
    else:
        draw.rounded_rectangle((36, 48, 220, 174), radius=14, fill='#183A46')
        draw.rounded_rectangle((49, 61, 207, 157), radius=5, fill='#D7F0EE')
        draw.rectangle((112, 173, 144, 199), fill='#183A46')
        draw.rounded_rectangle((78, 197, 178, 211), radius=6, fill='#183A46')
    save(image.resize((64, 64), Image.Resampling.LANCZOS), root / 'icons' / f'{name}.png')
