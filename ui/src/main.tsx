// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { cartoonCursorCss } from "./cursor";
import "./styles.css";

const cursorStyle = document.createElement("style");
cursorStyle.textContent = cartoonCursorCss();
document.head.append(cursorStyle);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
