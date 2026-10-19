# Schoolbook

Schoolbook is a locked-down Linux learning environment for children sharing a laptop. The machine boots into a kiosk. The child talks with a tutor, sees a full-screen board, watches vetted videos, and can open a short list of educational apps. A parent console on a separate port shows what happened.

Version 0.14.1 prevents repeats even after early dismissal and preserves the requested video subject in the software described in [docs/design-spec.md](docs/design-spec.md). Version 1.0.0 waits for a real pilot with a parent nearby. `schoolbook` starts a cage kiosk for the current session. It does not replace the machine's login manager; `packaging/install.sh` is the path that boots straight into Schoolbook.

## Layout

- `daemon/` — `schoolbookd`, the tutor, database, and HTTP API
- `session/` — `schoolbook-session`, the allowlisted app launcher
- `protocol/` — shared message models, package 1.3.0 / wire protocol major 1
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

Install `cage`, Chromium, and espeak-ng (`sudo apt install cage chromium espeak-ng` on Debian). Build the UIs once, then start everything with one command:

```bash
(cd ui && npm ci && npm run build)
(cd console && npm ci && npm run build)
uv sync --frozen
uv run schoolbook --parent-password 'choose-a-parent-password'
```

That starts the daemon and opens Chromium inside cage. Hold the top-right corner for five seconds, enter the parent password, and choose **End session** to leave. Later runs can omit `--parent-password` if the runtime under `~/.local/share/schoolbook` already exists.

After choosing a learner, the microphone listens until ten seconds of quiet; tap it to resume. Speak, pause, and the tutor answers out loud. It does not show written menus. The tutor finishes a sentence before it listens again. When the child asks for a video, the tutor searches YouTube, vets a candidate, and plays it; it does not ask for a video ID. Set `OPENAI_API_KEY` in a gitignored `.env` for live speech-to-speech (OpenAI Realtime). Video search also needs `YOUTUBE_API_KEY`. Claude's consumer voice mode cannot be embedded; typed `--dev` turns can still use `ANTHROPIC_API_KEY`. On an existing desktop, Schoolbook skips cage and opens Chromium `--kiosk` directly; Super or Alt-Tab may still reach other apps. Run from a TTY for a full lock.

`schoolbookd --config` still serves only the HTTP API if you need that without cage.

## Learner profiles

Choose **Arum** (flower) or **Hannah** (star) on the home screen. Use **Change learner** on the main talk screen to return to that chooser. Switching closes the previous conversation, stops any media or game, and starts with the selected child’s own history. The active learner is remembered across daemon restarts; the kiosk still opens to the chooser.

Hannah uses the **age-4** profile: short, concrete explanations, one idea at a time, no assumed reading or typing ability, and gentle preschool video searches aimed at ages 3–5. Videos are limited to 1–8 minutes; educational songs and animation are welcome. Pictures also use the learner’s age. These are selection preferences and metadata checks, not a guarantee of every video’s suitability. Arum keeps the existing age-six profile. Saved conversations, notes, learning progress, familiar songs, and watched-video records belong to each child separately.

In the parent console, **Viewing learner** selects whose records and profile you are viewing or editing; it does not switch the child on the laptop. Content blocks, app settings, tutor name, volume, and billing remain shared. Session controls act on the child currently using the laptop and are disabled when viewing another learner.

`profiles/learners.yaml` seeds additional learners once without overwriting parent edits. Hannah’s birth year is initially approximated as 2022 from her stated age; the explicit `age-4` teaching profile controls behavior, independently of birth year. Profile guidance lives in `profiles/age-4.yaml` and `profiles/age-6.yaml`.

## CF-30 kiosk controls

The **Wi-Fi** button at the top right opens connection status and nearby networks. Choose a network, enter its password if needed, and select **Join**. **Refresh networks** checks again; **×** or Escape closes the panel. Opening settings during a conversation pauses listening; tap the microphone to resume. The button is hidden during videos, songs, and games. The hidden parent-unlock area sits immediately to its left on the talk screen. Network selection requires NetworkManager to manage the Wi-Fi interface. The current CF-30 uses ifupdown, so its settings panel reports Wi-Fi unavailable; its existing connection remains usable. Migrating networking requires a separate maintenance window with local recovery access.

Every kiosk launch (including F11 recovery) fetches a fresh entry page so Chromium cannot keep an older UI after an update. HTML entry pages are not cached; hashed scripts, styles, and fonts can still use the browser cache.

On the CF-30, kiosk startup also clears the Panasonic firmware mute, which is separate from the normal Linux volume controls and can remain set after changing operating systems. It is cleared once per kiosk start, so the hardware mute key still works during use.

Tap the **microphone** to cancel the current speech attempt and start a fresh connection. Tap the **stop sign** to cancel the attempt and immediately silence the tutor; listening stays paused until the microphone is tapped again. A fresh connection clears the live AI conversation context, while saved learner data and transcripts remain. Connection setup and network waits do not block these controls. A disconnected browser can reconnect on the next microphone tap.

If speech stops immediately because OpenAI reports exhausted API credit, the child screen explains that a grown-up must replenish the account at [OpenAI API billing](https://platform.openai.com/settings/organization/billing/). After adding credit, tap the microphone again; rebooting cannot fix an exhausted account. Speech connection failures also show a visible retry message.

For each speech turn, the finalized transcription shown on screen replaces the corresponding audio message in the tutor’s conversation before a reply is requested. This gives the tutor the same words the parent sees, rather than a separate interpretation of the audio. Names, numbers, and meaningful words are preserved. Unrecognized audio is discarded; a transcription failure shows a recoverable microphone error. Spoken replies still use OpenAI Realtime audio.

Listening pauses automatically after ten seconds of quiet while the tutor is ready for another turn. Active speech, server-detected speech, tutor processing, and queued speech playback reset that timer. Tap the microphone to resume with a fresh conversation connection. Background noise may keep listening active; this is a quiet-time limit, not a hard recording cutoff. Long transcripts dominated by repeated phrases are rejected before they are saved as child speech or used to generate a tutor reply. Speech errors stop microphone capture and cancel the current attempt until the child retries.

Version 0.13.0 adds migration `0004` and the SQLite `api_usage` table for per-learner Realtime response and transcription usage, including cached/text/audio token details when supplied by OpenAI. Records contain model names, event identifiers, timestamps, and numeric counters, without transcript text or credentials. Learner deletion removes these records. These counters start with the update, are not yet displayed in the parent console, and are not an invoice: image requests and usage lost during abrupt disconnection are not included. Rejecting a bad completed transcript prevents downstream tutor usage but cannot undo the transcription charge. The current Realtime model and voice remain unchanged.

While a song or video is playing, microphone capture is stopped and the backend ignores speech input, so talking cannot interrupt playback. Pause or close the player to talk to the tutor again.

The main screen shows the laptop's battery percentage at the top left, with a lightning bolt while charging and a red indicator at 20% or below when discharging. It refreshes every 30 seconds and is hidden while a video, song player, or game is open. Machines without readable battery information show no indicator.

In the CF-30's systemd-managed X11/Openbox kiosk, **F11 restarts Schoolbook**, including the tutor backend, browser, audio session, and any open game. The current conversation is interrupted, but the laptop does not reboot and saved learner data remains. The key is handled by Openbox, so it can recover a frozen browser. It requires the root-run `schoolbook-kiosk.service` and `packaging/xinitrc`; it is not a shortcut in ordinary desktop or Cage sessions. An OS or X server freeze still needs separate recovery.

For an existing CF-30 installation, update the application and rebuild `ui/`, including `packaging/openbox/rc.xml`. Install the updated `packaging/systemd/schoolbook-kiosk.service` in `/etc/systemd/system/` and run `systemctl daemon-reload` as root; its ten-second stop timeout bounds recovery from stuck processes. The Openbox binding takes effect on the next kiosk start. Arrange that restart for a break in use; avoid restarting the kiosk while a child is using it.

## Video history and music controls

Both music and video players show large **− / + volume buttons** and a slider at the top. Each button changes volume by 10 percentage points; the slider covers 0% (silent) to 100%. The setting is shared between songs and videos and saved in the kiosk browser, including across tracks and restarts. It changes media playback volume only; tutor speech and system volume are unaffected. Adjusting volume does not pause playback or enable the microphone.

Video playback hides the video volume controls and red **×** along with the idle cursor. Moving the mouse or touching the player reveals them for two seconds after the last movement. Paused-video controls and music controls remain visible.

The child’s song screen has a large **pause/play** button. Pausing allows speech again; resuming stops microphone capture. Closing a song cancels the remaining queue.

Video watch history is separate from music history. A video counts as watched only after at least 50% of its distinct content has actually played in that viewing. Pauses, buffering, seeking over content, and replaying the same short segment do not add coverage. The browser reports the halfway milestone once; the daemon checks the current video and duration before saving it per learner in SQLite. Search results include `watch_count` and `last_watched_at`; general requests receive unseen videos only. The tutor can also call `get_video_history` to identify a specifically requested repeat. Old play counts are not converted because they do not establish half-watched completion. Migration `0003` adds `video_watches`; existing song and learner data remain intact.

Version 0.14.0 makes unseen videos the rule for general requests: searches exclude the child’s complete saved watch history, and playback checks it again even for an ID from an older result. When cached choices run out, the catalog fetches up to three additional YouTube pages per search, caches the results and continuation token across restarts, and refreshes exhausted searches after 24 hours. If no suitable new video is found, the tutor tries another relevant query or explains that it found none; it cannot silently substitute a watched video. The 50% threshold and separate per-child histories are unchanged.

Version **0.14.1** also records every successful non-music video selection in `video_selections` (migration `0005`). This is separate from a watch: stopping after a few seconds, a failed player load, or never reaching halfway still prevents automatic selection again. Search and playback exclude the union of selections and halfway watches for the current learner, across sessions and restarts. `get_video_history` includes `selection_count`, `last_selected_at`, `watch_count`, and `last_watched_at`, so early dismissals do not falsely count as watched. Explicitly requesting that particular video can retry or replay it. Existing global play counts are not backfilled into child histories because they do not identify which child selected the video or distinguish songs.

Version 0.14.1 retains the full spoken video request, including later corrections and subtopics. Search results preserve YouTube relevance rather than boosting familiar documentary channels; cached approved fallback videos must match all meaningful query words. Spoken-session tool calls are saved against the child turn in `tool_calls`, including queries, returned candidates, selected IDs, and refusal reasons. Inspection and tests do not require playing audio on the kiosk.

For a specific repeat, `get_video_history` accepts a title-fragment `query` to find older entries. `search_videos` can return one `requested_video_id` from that history when accompanied by `replay_request`, quoting the child’s current request. `play_video` requires the same request for a previously selected or watched video. The runtime verifies the actual child transcript and a specific title or reference to the last video, including a yes to a tutor’s specific clarification question. Permission is consumed when playback begins. A general topic/channel request is insufficient; ambiguous requests need clarification. Parent blocks, vetting, and age restrictions still apply. Song history and familiar-song replay are unchanged.

Schoolbook records a song after its audio actually starts, once per play (pausing/resuming does not count twice). History is saved per learner in SQLite and survives restarts. Requests such as “I want to hear some music” use `play_music` to shuffle previously heard, still-approved songs and play each once. Naming a song keeps the existing search-and-play behavior. If there is no history yet, the tutor asks which song to play. History begins with this update; old video play counts cannot reliably distinguish songs. Parent blocks are rechecked before each queued track. Album requests such as “Play the album Ugly is Beautiful by Oliver Tree” use YouTube Music release metadata (via `ytmusicapi`) plus the existing YouTube API key to verify the exact album, artist, and playable tracks. The complete album plays in release order, audio only, with the same pause/play controls and muted microphone during playback. Missing title or artist information prompts a question; an unavailable, incomplete, or blocked album produces an explanation instead of unrelated search results. A clean edition is preferred when listed with the same title. Album lookup needs network access to YouTube Music and Google APIs; no additional account is required. Migration `0002` adds `song_plays` without changing existing learner records.

## Parent console on romptele.com

Open **https://romptele.com/schoolbook/** on a phone or another laptop and use the existing Schoolbook parent password. The responsive console has Today, saved conversations, Progress, Memory, Library, Apps, Session, Learner, and Settings. Session timestamps use America/New_York time (EST in winter, EDT during daylight saving), regardless of the viewing device’s timezone. Use **Refresh** for current information and **Lock console** when finished. Ending a child’s session requires confirmation. The old Pause control is omitted because it did not pause the Realtime speech path reliably.

The built console is hosted on romptele.com; authenticated API requests travel over a separate reverse SSH tunnel to the CF-30’s loopback-only parent API. The CF-30 must be on, online, and running Schoolbook to view its data or use controls. Keep its system clock synchronized: the deployed CF-30 uses `systemd-timesyncd` with NTP enabled (`timedatectl show -p NTPSynchronized` should report `yes`). Timezone formatting cannot repair timestamps previously recorded with an incorrect system clock. No learner database or AI keys are copied into the public website. API responses are not cached; HTTPS cookies are Secure, HttpOnly, SameSite=Strict and scoped to `/schoolbook/`. Cross-origin API requests are rejected. The existing parent password/idle-lock checks remain in force.

Deployment (independent of the kiosk restart):

1. Build `console/` with `npm ci && npm run build`, and copy `console/dist/` to `/var/www/schoolbook-console/` on romptele.com.
2. Install `packaging/systemd/schoolbook-console-tunnel.service` in `/etc/systemd/system/` on the CF-30. As root, run `systemctl daemon-reload` and `systemctl enable --now schoolbook-console-tunnel.service`. It uses the already configured SSH identity and verified romptele.com host key; its separate loopback listener is `127.0.0.1:28766` on the server. It does not restart the existing SSH tunnel or kiosk.
3. Include `packaging/nginx/schoolbook-http.conf` in nginx’s `http` context and `schoolbook-locations.conf` inside romptele.com’s HTTPS server block. The live infrastructure copies belong in `/home/henry/webserver/nginx/conf.d/` and `/home/henry/webserver/nginx/snippets/`, respectively. Test with `sudo nginx -t`, then gracefully reload nginx. Do not expose port 28766 publicly.
4. Verify `/schoolbook/` serves the login page and `/schoolbook/api/today` returns 401 before login. To disable remote access, stop/disable only `schoolbook-console-tunnel.service`; local Schoolbook continues running.

Console assets and API requests use relative paths, so the same build still works directly at `http://127.0.0.1:8766/`. Changing the hosted path also requires updating the nginx locations and cookie scope.

## GCompris activities on Debian / the CF-30

Install `gcompris-qt` (including its matching `gcompris-qt-data` dependency) and `python3-tk` with the system package manager. Run `python3 packaging/setup-gcompris.py` **as the account running the kiosk** (currently root on the CF-30). It installs and checks the official English and US English voices, word images, and music resource packs, configures US English speech, disables background music and startup downloads, and preserves activity progress. Assets remain available offline. Rerun it to refresh those assets.

The shipped manifest describes all 196 activities in Debian Trixie's GCompris 25.0.12. The tutor selects a manifest activity and launches `gcompris-qt --enable-kioskmode -f --renderer=software --launch ACTIVITY`. Debian's `/usr/games` is searched even if absent from the service PATH. Only installed applications are advertised. A missing activity is rejected instead of opening the suite's landing page.

Ask for “the falling letters typing game” (`gletters`) or “the train game that says a letter” (`click_on_letter`; `click_on_letter_up` uses capitals). The tutor can search activity titles and descriptions. The full suite is installed locally; the tutor launches one chosen activity directly. GCompris's Home button exits a directly launched activity. Schoolbook also supplies a red **×** at the bottom right, leaving the top-right repeat-letter speaker unobstructed. Exiting either way returns to the tutor and restores listening. F11 still restarts the kiosk if needed.

Launching or exiting an activity does **not** prove the child completed it. Requiring learning activities before music/videos is not enabled; reliable activity-completion reporting and parent-configured requirements would be needed before adding that feature.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
