# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from schoolbookd.overlay import CLOSE_MARGIN, CLOSE_SIZE, close_button_geometry


def test_close_button_sits_in_the_top_right_corner() -> None:
    left, top, width, height = close_button_geometry(1920, 1080)
    assert (width, height) == (CLOSE_SIZE, CLOSE_SIZE)
    assert top == CLOSE_MARGIN
    assert left == 1920 - CLOSE_SIZE - CLOSE_MARGIN
