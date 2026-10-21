// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import type { BoardElement } from "./protocol";

export function Board({ elements }: { elements: BoardElement[] }) {
  return (
    <div className="board" aria-label="board">
      {elements.map((element, index) => (
        <BoardItem key={index} element={element} />
      ))}
    </div>
  );
}

function BoardItem({ element }: { element: BoardElement }) {
  if (element.type === "big_text") {
    return <p className="big-text">{element.text}</p>;
  }
  if (element.type === "letter_tiles") {
    return (
      <div className="tiles">
        {element.letters.map((letter) => (
          <button key={letter} type="button" className="tile">
            {letter}
          </button>
        ))}
      </div>
    );
  }
  if (element.type === "number" || element.type === "equation") {
    return <p className="equation">{element.type === "number" ? element.value : element.text}</p>;
  }
  if (element.type === "dots" || element.type === "objects") {
    const glyph = element.emoji || "●";
    return <p className="dots">{glyph.repeat(element.count)}</p>;
  }
  if (element.type === "number_line") {
    return (
      <p className="number-line">
        {element.start} to {element.end}
      </p>
    );
  }
  if (element.type === "image") {
    return <img className="board-picture" src={`/pictures/${element.image_id}`} alt={element.image_id} />;
  }
  if (element.type === "shapes") {
    return (
      <div className="shapes">
        {(element.items ?? []).map((item) => (
          <span key={item.shape} className={item.shape} style={{ color: item.color }}>
            {item.shape}
          </span>
        ))}
      </div>
    );
  }
  return null;
}
