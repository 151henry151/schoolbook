#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

say() {
  printf 'schoolbook kiosk-boot: %s\n' "$1"
}

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    say "would run: $*"
  else
    "$@"
  fi
}

here="$(cd "$(dirname "$0")" && pwd)"

if [[ "$DRY_RUN" != "1" && "${EUID}" -ne 0 ]]; then
  echo "schoolbook kiosk-boot: re-run with sudo, or pass --dry-run" >&2
  exit 1
fi

say "install NetworkManager so a parent can pick a guest Wi-Fi"
say "keep saved home Wi-Fi and use DHCP for new networks"
say "hide the GRUB menu and boot Debian 13 first"
say "hold Shift after power-on to pick the older Jessie install"
say "disable the login prompt and autologin the kiosk"
say "start Schoolbook on tty1 after boot"

if [[ "$DRY_RUN" == "1" ]]; then
  say "done"
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
run apt-get install -y --no-install-recommends network-manager grub-pc os-prober
run systemctl disable --now networking.service || true
run systemctl disable --now wpa_supplicant.service || true
run systemctl enable --now NetworkManager.service

if [[ -f /etc/network/interfaces ]]; then
  run sed -i -e 's/^auto wlan0/# auto wlan0/' -e 's/^allow-hotplug wlan0/# allow-hotplug wlan0/' \
    /etc/network/interfaces
fi

wpa_conf=/etc/wpa_supplicant/wpa_supplicant.conf
if [[ -f "$wpa_conf" ]]; then
  home_ssid="$(awk -F= '/^[[:space:]]*ssid=/{gsub(/"/, "", $2); print $2; exit}' "$wpa_conf")"
  home_psk="$(awk -F= '/^[[:space:]]*psk=/{gsub(/"/, "", $2); print $2; exit}' "$wpa_conf")"
  if [[ -n "$home_ssid" && -n "$home_psk" ]]; then
    if ! nmcli -g NAME connection show | grep -Fxq "$home_ssid"; then
      nmcli connection add type wifi ifname wlan0 con-name "$home_ssid" ssid "$home_ssid" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$home_psk" \
        ipv4.method manual ipv4.addresses 192.168.40.253/24 ipv4.gateway 192.168.40.1 \
        ipv4.dns 192.168.40.1 connection.autoconnect yes >/dev/null
    fi
  fi
fi

if [[ -f /etc/default/grub ]]; then
  run cp "$here/grub/default" /etc/default/grub
  run grub-install /dev/sda
  run update-grub
fi

if [[ -x /root/start-schoolbook.sh ]]; then
  run install -m 644 "$here/systemd/schoolbook-kiosk.service" /etc/systemd/system/schoolbook-kiosk.service
  run mkdir -p /run/user/0
  run chmod 700 /run/user/0
  run systemctl daemon-reload
  run systemctl disable --now getty@tty1.service || true
  run systemctl enable schoolbook-kiosk.service
fi

say "done"
