# Schoolbook

Schoolbook is a locked-down Linux learning environment for one child. The machine boots into a kiosk. The child talks with a tutor, sees a full-screen board, watches vetted videos, and can open a short list of educational apps. A parent console on a separate port shows what happened.

Version 0.9.0 is the software described through phase 8 of [docs/design-spec.md](docs/design-spec.md). Version 1.0.0 waits for a real pilot with a parent nearby. `schoolbook` starts a cage kiosk for the current session. It does not replace the machine's login manager; `packaging/install.sh` is the path that boots straight into Schoolbook.

## Layout

- `daemon/` — `schoolbookd`, the tutor, database, and HTTP API
- `session/` — `schoolbook-session`, the allowlisted app launcher
- `protocol/` — shared message models, protocol major 1
- `ui/` — the child's screen
- `console/` — the parent console
- `prompts/`, `profiles/`, `skills/`, `apps.d/` — shipped content
- `packaging/` — installer, greetd, Chromium policy, systemd, polkit

## Develop

```bash
uv sync --frozen
uv run ruff check protocol daemon session
uv run mypy --strict protocol/src daemon/src session/src
uv run pytest --override-ini='addopts='
uv run reuse lint
```

Build the web apps from `ui/` and `console/` with `npm ci`, `npm test`, and `npm run build`. End-to-end tests live in `e2e/` and need those builds plus Chrome:

```bash
cd e2e && npm ci && npx playwright test
```

`packaging/install.sh --dry-run` prints the lockdown steps. Run the script with sudo only on a machine you intend to turn into a kiosk.

## Run the kiosk

Install `cage` and Chromium (`sudo apt install cage chromium` on Debian). Build the UIs once, then start everything with one command:

```bash
(cd ui && npm ci && npm run build)
(cd console && npm ci && npm run build)
uv sync --frozen
uv run schoolbook --parent-password 'choose-a-parent-password'
```

That starts the daemon and opens Chromium inside cage. Hold the top-right corner for five seconds, enter the parent password, and choose **End session** to leave. Later runs can omit `--parent-password` if the runtime under `~/.local/share/schoolbook` already exists.

Speech-to-text is still the fake provider, so the developer text box is on by default. Pass `--no-dev` to hide it. On an existing desktop, cage runs nested and the host compositor may still allow Super or Alt-Tab; run `schoolbook` from a TTY for a full lock.

`schoolbookd --config` still serves only the HTTP API if you need that without cage.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
