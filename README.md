# Schoolbook

Schoolbook is a locked-down Linux learning environment for one child. The machine boots into a kiosk. The child talks with a tutor, sees a full-screen board, watches vetted videos, and can open a short list of educational apps. A parent console on a separate port shows what happened.

Version 0.9.0 is the software described through phase 8 of [docs/design-spec.md](docs/design-spec.md). Version 1.0.0 waits for a real pilot with a parent nearby. This repository does not apply kiosk lockdown to the machine it is developed on.

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

## Run a local daemon

Point `schoolbookd --config` at a YAML file with `data_dir`, `share_dir` (this repository), and `etc_dir` (learner, apps, output check, secrets). `schoolbookd --check-config` refuses a bad file. `schoolbookd --self-test` opens the database and speaks a sample. `schoolbookd serve` listens on `127.0.0.1` for the child and, unless LAN access is enabled, on `127.0.0.1` for the console.

Add `?dev=1` to the child UI to type instead of using the microphone. API keys stay write-only in the console.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
