// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Schoolbook contributors

import { useEffect, useState } from "react";

type Battery = { percent: number; charging: boolean };

export function BatteryIndicator() {
  const [battery, setBattery] = useState<Battery | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    async function update() {
      try {
        const response = await fetch("/battery", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("battery unavailable");
        const data = (await response.json()) as Partial<Battery>;
        if (active) {
          setBattery(
            typeof data.percent === "number" && Number.isFinite(data.percent) && data.percent >= 0 && data.percent <= 100
              ? { percent: Math.round(data.percent), charging: data.charging === true }
              : null,
          );
        }
      } catch {
        if (active) setBattery(null);
      } finally {
        if (active) timer = setTimeout(() => void update(), 30_000);
      }
    }
    void update();
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, []);

  if (!battery) return null;
  const low = battery.percent <= 20 && !battery.charging;
  const label = `Battery ${battery.percent}%${battery.charging ? ", charging" : low ? ", low" : ""}`;
  return (
    <div className={`battery-indicator${low ? " is-low" : ""}`} role="img" aria-label={label} title={label}>
      <svg viewBox="0 0 52 28" aria-hidden="true">
        <rect x="2" y="3" width="42" height="22" rx="4" fill="none" stroke="currentColor" strokeWidth="3" />
        <path d="M48 9v10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
        <rect x="6" y="7" width={34 * battery.percent / 100} height="14" rx="1" fill="currentColor" />
        {battery.charging ? <path d="M26 3l-9 13h7l-2 10 12-15h-8z" fill="#f6efe2" stroke="#1c1915" strokeWidth="1.5" /> : null}
      </svg>
      <span aria-hidden="true">{battery.percent}%</span>
    </div>
  );
}
