# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Board elements the tutor may place on screen. No URLs, capped text."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_URL = re.compile(r"(https?://|www\.)", re.IGNORECASE)


def reject_url(value: str) -> str:
    if _URL.search(value):
        raise ValueError("URLs are not allowed on the board")
    return value


class BigText(BaseModel):
    type: Literal["big_text"] = "big_text"
    text: str = Field(min_length=1, max_length=80)
    highlights: list[int] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return reject_url(value)


class LetterTiles(BaseModel):
    type: Literal["letter_tiles"] = "letter_tiles"
    letters: list[str] = Field(min_length=1, max_length=16)

    @field_validator("letters")
    @classmethod
    def _letters(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for letter in value:
            if len(letter) != 1 or not letter.isalpha():
                raise ValueError("letter tiles must be single letters")
            cleaned.append(letter.lower())
        return cleaned


class NumberElement(BaseModel):
    type: Literal["number"] = "number"
    value: str = Field(min_length=1, max_length=32)

    @field_validator("value")
    @classmethod
    def _value(cls, value: str) -> str:
        return reject_url(value)


class Equation(BaseModel):
    type: Literal["equation"] = "equation"
    text: str = Field(min_length=1, max_length=40)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return reject_url(value)


class Dots(BaseModel):
    type: Literal["dots"] = "dots"
    count: int = Field(ge=0, le=20)
    emoji: str = Field(default="●", max_length=8)


class Objects(BaseModel):
    type: Literal["objects"] = "objects"
    count: int = Field(ge=0, le=20)
    emoji: str | None = Field(default=None, max_length=8)
    image_id: str | None = Field(default=None, max_length=64)


class Hop(BaseModel):
    start: int
    end: int


class NumberLine(BaseModel):
    type: Literal["number_line"] = "number_line"
    start: int
    end: int
    marks: list[int] = Field(default_factory=list)
    hops: list[Hop] = Field(default_factory=list)

    @model_validator(mode="after")
    def _range(self) -> NumberLine:
        if self.end <= self.start:
            raise ValueError("number line end must be greater than start")
        return self


class ImageElement(BaseModel):
    type: Literal["image"] = "image"
    image_id: str = Field(min_length=1, max_length=64)


class ShapeItem(BaseModel):
    shape: Literal["circle", "square", "triangle", "star"]
    color: str = Field(min_length=1, max_length=20)

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        return reject_url(value)


class Shapes(BaseModel):
    type: Literal["shapes"] = "shapes"
    items: list[ShapeItem] = Field(min_length=1, max_length=12)


BoardElement = Annotated[
    BigText
    | LetterTiles
    | NumberElement
    | Equation
    | Dots
    | Objects
    | NumberLine
    | ImageElement
    | Shapes,
    Field(discriminator="type"),
]


class Board(BaseModel):
    elements: list[BoardElement] = Field(max_length=8)
