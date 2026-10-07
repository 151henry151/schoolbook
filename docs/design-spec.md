# Schoolbook — Design & Implementation Spec

Oct 7, 2026 · @Henry

## 1. Overview

Schoolbook is a locked-down Linux learning environment where a child talks out loud with an AI tutor that teaches, shows things on screen, plays curated videos and launches approved educational apps. Version 1 targets one six-year-old on a spare Panasonic Toughbook. The design assumes from day one that it will later serve other ages, other families and other Linux machines.

**What a parent gets:** turn the laptop on, and the child lands in Schoolbook. Nothing else on the machine is reachable without the parent password. Everything the tutor says and does is logged and reviewable.

**What the child gets:** a friendly voice he can talk to about anything he is curious about. It explains things at his level, asks him questions, shows pictures and words big on the screen, plays a short video when one helps, and opens games like GCompris when it is time to practice.

### Goals for v1

1. Boot straight into a kiosk session with no way out except the parent password.
2. Spoken, turn-taking conversation with the tutor, tuned for a six-year-old's speech and attention span.
3. The tutor can show content on a full-screen "board", search all of YouTube and choose and vet videos itself, launch allowlisted apps, and see what happens on screen while the child plays or watches.
4. The tutor keeps a persistent learner model: interests, skills, what is mastered and what needs work.
5. A parent console for transcripts, progress, the tutor's video choices and why, blocks and settings.
6. Runs on modest hardware (an older Core i5 with 4–8 GB RAM) and on any mainstream Linux desktop.

### Non-goals for v1

- No open web browsing, ever, from the child's side.
- No social features, chat with other people, or accounts on remote services.
- No hosted multi-family service. Schoolbook is software a family installs on its own machine (see section 10 for why this matters).
- No camera input. Microphone and screen only.
- No native mobile or Windows/macOS builds.

## 2. Guiding principles and the learning experience

The tutor follows the child's curiosity and weaves teaching into it; it never runs a fixed lesson plan. This fits an unschooling household and is also what keeps a six-year-old engaged.

### Principles

- **Child leads, tutor scaffolds.** The child picks the topic. The tutor connects it to skills (a question about volcanoes becomes counting, new words, cause and effect) and nudges toward weak areas only by offering choices. Explanations and especially videos aim a step past what he already understands, and the tutor bridges the gap.
- **Short turns, real conversation.** One or two short sentences per turn, then hand the floor back. A question, a choice, or "want to see?" ends most turns.
- **Show, don't just tell.** Anything with a shape (a number, a word, an animal, a map) goes on the board in big type or a picture.
- **Effort over correctness.** Praise trying and noticing. Mistakes are interesting, never wrong in a scolding way.
- **No time limits.** Sessions run as long as he is learning and enjoying it. The tutor never pads a session to keep him on; it notices tiredness or frustration and suggests moving around, a snack, or an off-screen mission ("go find three round things in the kitchen") the way a good human tutor would.
- **Grown-ups stay in the loop.** The tutor never asks the child to keep secrets, never discourages talking to parents, and points to a grown-up for anything about safety, feelings or the body.
- **Transparent to parents.** Every utterance, tool call and memory update is logged and visible in the parent console.

### What a session looks like

1. The child taps a big picture button with his face or avatar (one learner today, several later). The tutor greets him by name and recalls one thing from last time ("Last time we found out sharks are older than trees!").
2. It offers two or three choices drawn from his interests and from skills that need practice, plus "or tell me what you're wondering about."
3. Conversation runs in short turns. The tutor puts words, numbers or pictures on the board and asks him to read, count, or point.
4. When practice helps, the tutor launches a matching GCompris activity or another app. While he plays, the tutor watches the screen, so when Schoolbook comes back it already knows how it went ("You got to level 4 on the counting game! The 9s were tricky, huh?").
5. When a video helps, the tutor searches YouTube, vets the candidates, and picks one pitched a little above his current level. It watches along, pauses to explain the hard parts, and talks about it with him afterwards.
6. When he says goodbye or wanders off for a while, the tutor closes with a short recap. There is no time limit. The parent console receives a session summary.

### Subject coverage

The tutor draws on everything: early math, reading and phonics, writing, science, history, geography, music, art, computer science (sequencing, patterns, simple logic), and philosophy for children (fairness, "how do we know?"). A skills map (section 8) gives structure for tracking. It is a map of what is possible, not a syllabus.

## 3. System architecture

Schoolbook is two cooperating processes running as two different Linux users. A privileged-but-headless daemon holds the API keys, the database and all decision-making. An unprivileged session agent runs the child's screen. The child's account never sees a secret, and nothing the child can touch can reach the open internet except through the daemon.

&#91;embedded content: Schoolbook architecture · 2 users, 1 daemon, 3 outside services\]

The kiosk side only displays, captures and launches; every call to Claude, speech providers and the YouTube API goes through the daemon, which checks each action against policy first.

### Components

| Component | Runs as | Responsibility |
| --- | --- | --- |
| `schoolbookd` | system user `schoolbook` (systemd service) | Tutor loop, Claude API calls, STT/TTS providers, tool execution, learner model, SQLite DB, parent console HTTP server, policy enforcement, YouTube search and vetting, analysis of screen observations |
| `schoolbook-session` | kiosk user `kid` (inside the kiosk compositor) | Starts and supervises the UI window, launches allowlisted apps on request, captures screen frames and playback audio for the observer, reports app start/exit, relays the parent-unlock gesture |
| Child UI | `kid`, inside a locked Chromium window | Full-screen React app: talk button, avatar, board, video player, home screen. Captures microphone and plays audio |
| Kiosk compositor | `kid` | `cage` (Wayland kiosk compositor). Fallback: Xorg + Openbox with a stripped keymap for hardware where Wayland misbehaves |
| Parent console | served by `schoolbookd` | Web UI on a separate port, password-protected. Reachable on the device via the unlock gesture, optionally from the parent's phone on the LAN |
| Providers | inside `schoolbookd` | Pluggable STT, LLM and TTS backends behind interfaces, with local and cloud options |

### Communication

- **UI ↔ daemon:** one WebSocket on `127.0.0.1`, authenticated with a per-boot token the daemon writes to a file only `kid` can read. It carries audio frames up, and transcript, board commands, audio chunks and state events down.
- **Daemon ↔ session agent:** a Unix domain socket in `/run/schoolbook/` with group permissions. The daemon sends `launch(app_id, args)` and `focus_home()`. The agent replies with `app_started`, `app_exited` and `unlock_requested`.
- **Daemon ↔ outside world:** HTTPS to the Anthropic API, the YouTube Data API, and any cloud STT/TTS provider. Video playback is the one exception: the child's browser loads video streams directly, but only through an allowlist enforced by browser policy.

### Technology choices

| Layer | Choice | Why |
| --- | --- | --- |
| Daemon | Python 3.12, asyncio, FastAPI + uvicorn | Your strongest language; best ecosystem for audio and ML providers; the Anthropic Python SDK |
| Storage | SQLite (WAL mode) + Alembic migrations, SQLAlchemy 2.x | Single machine, zero admin, easy backup; same ORM you already know |
| Child UI | React + TypeScript, Vite build, served as static files by the daemon | Known stack; video embeds and rich board content are easiest in a browser |
| UI host | Chromium in `--kiosk` mode with managed enterprise policies | Mature media support (YouTube needs H.264/VP9), built-in echo cancellation for the mic, URL allowlisting via policy |
| Compositor | `cage` | Purpose-built single-app Wayland kiosk; no panels, no app switcher, no shortcuts by default |
| Session agent | Python, small and dependency-light | Shares code (protocol models) with the daemon |
| Parent console | React app served by the daemon | Same component library as the child UI |
| Packaging | `.deb` + an install script first; Flatpak is a poor fit because the product configures system users and the session | Debian/Ubuntu/Mint cover most spare laptops |

**Alternative considered:** Tauri (Rust + WebKitGTK) for the UI host. It gives a native window and tighter navigation control, but WebKitGTK's video codec support depends on distro GStreamer packages. Chromium is the safer v1 choice. Revisit Tauri once the core works.

## 4. Kiosk session and lockdown

The machine boots, auto-logs into the `kid` account, and starts a compositor that can only show Schoolbook and the apps it launches. Lockdown is layered: the OS account has no privileges, the compositor has no escape keys, the browser has no navigation, and the firmware has no boot menu. No single layer has to be perfect.

### Accounts

- **`kid`**: no sudo, no shell login, password-locked, member of `audio`, `video` and `schoolbook-ui` only. Home directory holds app save files and nothing else.
- **`schoolbook`**: system user for the daemon. Owns `/var/lib/schoolbook` (DB, media cache) and `/etc/schoolbook/secrets.env` (mode 0600).
- **Parent admin account**: the normal sudo-capable account used for maintenance. Never auto-logged in.

### Boot to kiosk

1. `greetd` with an autologin `initial_session` for `kid` running `cage -- schoolbook-session`. Leaving out cage's `-s` flag disables VT switching inside the session.
2. `schoolbook-session` starts Chromium in kiosk mode pointed at the daemon's local UI, waits for the WebSocket handshake, then supervises it. A crashed browser restarts within two seconds.
3. If the session agent itself exits, cage exits and greetd restarts the autologin, so the child sees a brief blank screen, never a desktop.

### Escape vectors and mitigations

| Vector | Mitigation |
| --- | --- |
| Ctrl+Alt+F1–F12 (VT switch) | Cage without `-s`; `NAutoVTs=0` and `ReserveVT=0` in logind so no getty waits on other VTs |
| Ctrl+Alt+Del | Mask `ctrl-alt-del.target` |
| Magic SysRq | `kernel.sysrq = 0` |
| Power or lid buttons | Power key = clean poweroff (not an escape); lid = suspend; on resume the session is still locked |
| Browser navigation, new windows, devtools, `chrome://` pages | Chromium managed policy: `URLBlocklist: ["*"]` with a tight `URLAllowlist`, `DeveloperToolsAvailability: 2`, downloads, printing and incognito disabled, `chrome://*` blocked |
| A launched app opening a web link or file manager | `xdg-open` for `kid` replaced by a stub that logs the attempt and does nothing; no default browser or file manager registered for `kid` |
| App file dialogs | Acceptable risk: they can only browse `kid`'s home and world-readable system files. Prefer apps and activity modes that don't open dialogs |
| USB sticks | Polkit rule denying udisks mounts for `kid` |
| Terminal emulators | Not on the app allowlist; the session agent only executes allowlisted command lines, never arbitrary strings |
| Booting another OS or single-user mode | BIOS supervisor password, internal disk first in boot order, USB/network boot disabled, GRUB menu hidden and password-protected |

### Parent unlock

- **Gesture:** press and hold the top-right corner of the screen for 5 seconds, or Ctrl+Alt+Shift+P. A small dialog asks for the parent password. The tutor never mentions the gesture or the password.
- **Verification:** the daemon checks an Argon2id hash. After 5 failures, it locks for 5 minutes and logs the attempts.
- **Unlocked menu:** open the parent console, pause the session, end the session and log out to the greeter (to sign into the admin account), or shut down.
- **Auto-relock:** returning to the child view, or 5 minutes idle on the parent screen, locks again.

### Disk encryption

Full-disk encryption needs a passphrase at boot, which conflicts with "turn it on and it works." Options are TPM2-backed unlock (if the Toughbook has a TPM 2.0) or encrypting only `/var/lib/schoolbook` and the parent's home. Decide per machine; the installer asks.

## 5. Voice pipeline

Voice is a three-stage pipeline — speech-to-text, Claude, text-to-speech — because the Claude API takes and returns text, not audio. The design target is under 1.5 seconds from the end of the child's sentence to the first word of the reply on the cloud path, and every stage sits behind an interface so local and cloud providers can be swapped per machine.

### Turn-taking for a six-year-old

- **Default: tap-to-talk.** A big round button (also the space bar). Tap to start, tap again or pause for 1.5 s to finish. It is more reliable than always-listening with a young child, works in a noisy house, and the mic is never on when he isn't talking.
- **Optional: hands-free.** Voice activity detection decides turns, as in Claude's own voice mode. A parent setting, off by default.
- **Interrupting:** tapping the button while the tutor talks stops playback, cancels the in-flight Claude stream and starts listening.
- **Showing his words:** the transcript of what he said appears in large type under the button. This doubles as reading practice and lets him see when he was misheard.

### Flow of one turn

1. The browser captures mic audio with `getUserMedia` (echo cancellation and noise suppression on) and an AudioWorklet that emits 16 kHz mono 16-bit PCM frames over the WebSocket.
2. The daemon streams frames to the STT provider and receives a final transcript when the turn ends.
3. The tutor loop sends the conversation to the Claude Messages API with `stream: true` and the tool definitions (section 6).
4. Text deltas go into a sentence chunker. Each complete sentence goes to TTS immediately, so speech starts while Claude is still writing.
5. Tool calls run as they arrive. A `show_board` call reaches the screen before the sentence that refers to it is spoken.
6. Audio chunks stream to the browser, which plays them in order from a queue. Every event carries a turn ID so stale audio from a cancelled turn is dropped.

### Provider options

| Stage | Local option | Cloud option | Notes |
| --- | --- | --- | --- |
| Speech-to-text | `whisper.cpp` (base.en or small.en) or faster-whisper | Deepgram, AssemblyAI, ElevenLabs Scribe, OpenAI | Children's speech is harder to recognise than adults'. Benchmark on recordings of the actual child before choosing |
| LLM | none in v1 | Claude via the Messages API | Default `claude-haiku-5-5` for speed; parent setting to use `claude-sonnet-5-5` |
| Text-to-speech | Piper (fast on CPU, many voices) | ElevenLabs, Cartesia, OpenAI TTS | Pick one warm, slightly slow voice and keep it constant; children attach to a consistent voice |

**Recommended v1 configuration:** cloud STT (accuracy matters most with a young child), Claude Haiku, local Piper TTS (free, private, low latency). Re-evaluate after the pilot.

### Handling recognition errors

- Pass a hint vocabulary (the child's name, recent topic words) to STT providers that support keyword boosting.
- The tutor is told transcripts may be wrong and should check ("Did you say *shark* or *star*?") rather than guess about anything important.
- Very short or empty transcripts trigger a gentle "I didn't catch that" without a Claude call.

### Offline and failure behaviour

If the Claude API or STT is unreachable, the screen shows a friendly "the tutor is resting" message with the offline app shelf (GCompris and the other launchable apps). The daemon retries in the background and the tutor returns when the network does.

## 6. Tutor agent

The tutor is Claude running a standard tool-use loop. Its behaviour comes from a layered system prompt and its abilities come only from a fixed set of tools that the daemon validates. Claude never touches the OS, the network or the database directly. Every action is a tool call the daemon checks against policy before executing.

### System prompt layers

| Layer | Source | Changes | Cached |
| --- | --- | --- | --- |
| 1. Core charter: role, honesty, safety rules, tool etiquette | `prompts/core.md` in the repo | Per release | Yes (prompt caching) |
| 2. Age profile: language level, turn length, attention span, subject emphasis | `profiles/age-6.yaml`, rendered to text | Per learner config | Yes |
| 3. Learner summary: name, interests, strengths, skills in progress, notes from last sessions | Generated from the DB at session start | Per session | Yes, within the session |
| 4. Session state: elapsed time, what is on screen, app or video running, latest screen observations | Injected each turn | Per turn | No |

The core charter and age profile live in version-controlled files with tests (section 14). Parents can add free-text "house notes" ("we're vegetarian", "he's scared of thunderstorms") through the console; these render into layer 3.

### How the tutor talks (age-6 profile)

- At most two or three sentences per turn, each under about 12 words.
- Everyday words. A new word is said, explained once with an example, and reused.
- One question at a time, then stop and wait.
- Concrete before abstract: count real things, compare to things in his house.
- Spoken output only: no lists, markdown, emoji or symbols in speech. Anything visual goes through `show_board`.
- Hint ladder for practice: re-ask, then a hint, then a bigger hint, then do it together. Never just give the answer on the first miss.
- Celebrate effort and noticing, specifically ("You counted by twos!"), not generic "good job" on every turn.

### Honesty and boundaries

- The tutor is honest that it is a computer helper, not a person, an animal or a magic being. It can be warm and playful without pretending otherwise.
- It never asks for or repeats personal details (address, school, passwords) and never asks the child to keep a secret.
- Hard or sensitive topics (death, war, bodies, scary news, religion, politics) get a short, gentle, factual answer pitched at his age, and an invitation to talk about it with a grown-up. It does not take sides on contested beliefs.
- If the child expresses fear, sadness, being hurt, or that someone is hurting him, the tutor responds kindly, encourages him to tell a trusted grown-up now, and calls `flag_for_parent` with high severity. It does not investigate or ask leading questions.
- There are no time limits. It never stretches a session to keep him on, and it suggests a break when he seems tired, the way a person would.

### Tools

| Tool | What it does | Daemon-side guardrails |
| --- | --- | --- |
| `show_board(elements)` | Puts big text, letter tiles, numbers, counting dots, a number line, simple shapes, emoji pictures or a library image on screen | Schema-validated element types only; text length caps; no URLs; images only from the local image library |
| `ask_choice(prompt, options)` | Shows 2–4 big tappable answer buttons; the tap or a spoken answer returns as the tool result | Max 4 options, short labels |
| `search_videos(query, subject?)` | Searches all of YouTube and returns candidates with title, channel, length, description and frame thumbnails (section 7) | SafeSearch strict, embeddable only; Shorts and blocked channels removed before the tutor sees results |
| `play_video(video_id, start?, end?)` | Plays a video full screen; the tutor watches along and can pause, rewind or stop it | Video must have passed vetting and not be on the block list |
| `list_apps(subject?)` / `launch_app(app_id, activity?)` | Lists allowlisted apps and launches one, optionally at a specific activity | App ID and activity must be in the allowlist; the command line is built from config, never from model text |
| `get_skill_status(area?)` | Reads current mastery estimates for a skill area | Read-only |
| `record_observation(skill_id, outcome, evidence)` | Logs evidence of a skill: correct, with help, not yet | Skill must exist in the skills map |
| `note_interest(topic, strength)` / `note_for_next_time(text)` | Stores interests and short reminders for future sessions | Length caps; shown to parents |
| `request_content(kind, description)` | Asks parents for an app or local media it wishes it had | Goes to the approval queue; never fetches anything |
| `flag_for_parent(severity, reason)` | Alerts the parent console (and optionally the parent's phone) | Always allowed |
| `suggest_break()` / `end_session(summary)` | Winds the session down | `end_session` also triggers the post-session summary job |

Three more tools support videos and observation. vet\_video(video\_id) runs the vetting pipeline and returns a verdict, reasons and an estimated level. video\_control(action, at\_s) pauses, resumes, seeks or stops playback. get\_observations() returns what the screen observer has seen since the last call. App exits, video endings, observer summaries and button taps arrive as structured events in the next user turn, so the tutor can react ("You got to level 4! The 9s were tricky, huh?").

### Loop limits

- At most 6 tool calls per child turn, 20 s wall clock per turn, then the tutor must speak.
- Older turns in a long session are folded into a running summary so the context stays small and fast.
- Every model request and response, including tool calls, is written to the session log.

## 7. Content: videos, apps and the board

Videos come from all of YouTube, found and vetted by the tutor itself. Apps and images come from parent-controlled catalogs. In every case the tutor picks content by ID through tools; it never receives a URL or a command line it could rewrite.

### Videos from YouTube

The tutor searches all of YouTube and decides on its own what to show. Parents don't approve videos in advance. They see every pick with the tutor's reasons in the console and can block a video or a whole channel afterwards. Because this is the widest door in the system, every candidate passes a vetting pipeline before it can play, and the tutor keeps watching while it plays.

**Search.** `search_videos` calls the YouTube Data API `search.list` with `type=video`, `safeSearch=strict` and `videoEmbeddable=true`, then `videos.list` for details (duration, made-for-kids flag, channel, description). The daemon drops Shorts, live streams, blocked channels and videos it already rejected before the tutor sees the list. Each search costs 100 quota units, and a project's default allowance is about 100 searches a day ([YouTube quota costs](https://developers.google.com/youtube/v3/determine_quota_cost)). That is plenty for one child; results are cached per query.

**Vetting (`vet_video`)**, in order, stopping at the first failure:

1. **Hard filters (no model):** embeddable, not age-restricted, not live, not a Short, duration within a configurable window (default 1–30 minutes), channel not blocked, language matches.
2. **Metadata review (Claude):** title, description, tags, channel name and about page, made-for-kids flag. Rejects clickbait, kid-bait (familiar characters in strange or violent situations, "surprise" spam), heavy product promotion, and fringe or misleading takes on science and history.
3. **Visual review (Claude vision):** the main thumbnail plus YouTube's auto-generated frame thumbnails from different points in the video.
4. **Level estimate (Claude):** vocabulary, pace and prerequisite concepts, rated on the same scale as the learner model (section 8).
5. **Verdict:** approve or reject with written reasons, stored and cached. Channels build a reputation: repeated passes make a channel preferred; one failure demotes it.

**Why not transcripts up front:** the official API only lets a video's owner (or someone with edit rights) download its captions. Third-party transcript services and unofficial libraries exist but sit badly with YouTube's terms and break without warning. V1 doesn't depend on them; instead the tutor listens to the video as it plays (below). A transcript pre-check can be added later as an optional provider if you decide the trade-off is acceptable.

**Picking the stretch.** For the topic at hand, the tutor compares each candidate's estimated level with what the learner model says he has secure. It aims one step up: new ideas built on things he already knows, a handful of new words, narration at normal speed. It prefers videos where the gap is small enough that a pause and a sentence of explanation bridge it. Easy favourites are fine when he asks for them. After each video, a quick check ("What do you think made the volcano blow?") is recorded, and the stretch target moves up if he followed easily or down if he got lost.

**Watching along.** While a video plays, the session agent captures the speakers' output from PipeWire and streams it to STT, giving the tutor a live, timestamped transcript. The screen observer (below) adds what is on screen. With both, the tutor can:

- pause when a key new word or idea appears, explain it in a sentence or two, or ask "what do you think happens next?", at most every couple of minutes;
- answer questions when he taps pause, using what was just said and shown;
- stop the video at once if anything inappropriate appears, raise a flag, and block the video.

**Playback.**

- Embed through the IFrame Player API on the `youtube-nocookie.com` domain with `rel=0`. Since 2018, `rel=0` no longer hides end-of-video suggestions; it only limits them to the same channel ([YouTube embed reference](https://www.creatoressentials.com/glossary/youtube-embeds/)).
- So YouTube's own end screen and controls never take over. A transparent overlay covers the player; the child uses Schoolbook's big Play, Pause and Done buttons. On the `ENDED` state the player is destroyed and the tutor resumes.
- Ads can appear on videos that have them enabled. Vetting prefers channels without ads, and the console shows when one played.
- The Chromium allowlist permits only the domains the player needs; the exact list is captured in Phase 4 by watching network requests and pinned in policy.
- Schoolbook does not download YouTube videos, which conflicts with YouTube's terms. Local files the family owns or that are openly licensed can be added as a second source and are the offline path.

### App launcher

Each launchable app is a manifest in `/etc/schoolbook/apps.d/*.yaml`, written by the parent or shipped as a default:

```yaml
id: gcompris
name: GCompris
exec: [gcompris-qt, --enable-kioskmode, -f]
activity_arg: [--launch, "{activity}"]
level_arg: [--start-level, "{level}"]
observe: true            # screen observer on while this app is in front
activities:
  - id: algebra_by
    title: Multiplication practice
    skills: [math.multiplication.facts]
    ages: [7, 10]
  - id: enumerate
    title: Count the items
    skills: [math.counting.to20]
    ages: [4, 7]
```

GCompris supports exactly this: `--launch <activity>` starts a specific activity, `--start-level` picks its level, `-l` lists activity names, and `--enable-kioskmode` hides its Quit and Configuration buttons ([GCompris console switches](https://gcompris.net/docbook/stable6/en/console-switches.html)).

**Launch flow:** the tutor calls `launch_app("gcompris", "enumerate")`. The daemon checks the manifest and builds the argv from it (never from model text). The session agent spawns it in the kiosk session, the Schoolbook window steps back, and the screen observer starts. A floating "Home" button (a small always-on-top layer, or the parent gesture if the compositor can't keep it on top) lets the child return. When the app exits, the agent reports back and the observer's summary goes to the tutor.

**Seed app list (verify packaging per distro):** GCompris (180+ activities, ages 2–10), Tux Paint (drawing), KTurtle (first programming), Stellarium (night sky), Marble (globe and maps), and later Kiwix with a children's offline encyclopedia for older learners.

### Screen observation

The tutor knows how a game or video went because it watched, not because it asked. A screen observer samples what is in front of the child, and a vision model turns the samples into short structured notes the tutor reads like any other event.

- **Capture:** while an app or video is in front, the session agent grabs a frame every 3 seconds through the compositor's screencopy protocol (`grim` on wlroots compositors such as cage; confirm in the Phase 1 spike). A perceptual hash drops frames that barely changed.
- **Analysis:** every 30 seconds, or on a big screen change, the daemon sends the new distinct frames (downscaled) to Claude Haiku with the context (which app, activity and starting level). It returns a note: what is on screen, visible progress (level reached, score, right or wrong feedback), and signs of being stuck or finished.
- **Results:** notes go into the session log. When the app closes, a consolidated summary reaches the tutor as an event and becomes `record_observation` entries marked *observed* (weighted a bit lower than skills the tutor checked directly). If the same screen sits unchanged with repeated wrong answers for about a minute, the tutor can speak up over the app ("Want a hint?"); a parent setting turns this off.
- **App-specific extras:** GCompris starts at a known activity and level, which anchors the notes. Later plugins can read apps' own progress files where they keep them.
- **Privacy and cost:** frames live in memory only; just the analysed frames go to Anthropic, and nothing is written to disk unless a parent turns on a debug option. Cost grows with frames analysed, which the change detection keeps modest; interval and per-minute frame caps are settings.

### The board

The board is the full-screen visual area the tutor controls through `show_board`. Element types in v1:

| Element | Example use |
| --- | --- |
| `big_text` (with optional highlighted letters) | A word to read, sounding out "c-a-t" |
| `letter_tiles` (tappable) | Build a word, find the first letter |
| `number` / `equation` | 3 + 4 = ? |
| `dots` / `objects` (emoji or image, count up to 20) | Counting, grouping, comparing |
| `number_line` (range, marked points, hops) | Adding by jumping |
| `image` (from the local image library) | A volcano, a skeleton, a map of Vermont |
| `shapes` (circle, square, triangle, star, with colours) | Geometry, patterns, sequences |
| `choices` (via `ask_choice`) | Multiple choice with pictures |

The image library is a local folder of openly licensed images (for example OpenMoji and Wikimedia Commons) with a tag index; parents can add their own. Freehand drawing and handwriting input on touch screens come later (section 16).

## 8. Learner model and memory

The tutor's memory is structured data in SQLite, not a free-form diary. Skills, interests and short notes are each stored in their own tables, updated only through tool calls and a post-session job, and fully visible and editable by parents. At session start, a compact summary of about 1,500 tokens goes into the system prompt.

### Skills map

- A tree of skill IDs such as `math.counting.to20`, `math.addition.within10`, `reading.phonics.cvc_words`, `science.living_things.needs`, `cs.sequencing.instructions`, `philosophy.fairness`.
- Shipped as YAML (`skills/core.yaml`), each skill with a kid-friendly description, typical age band and prerequisites. Early math and literacy are seeded from common early-grades frameworks (for example Common Core K–2 and NGSS K–2) as a scaffold for tracking, not as a sequence the child must follow.
- Parents can add skills; future curriculum packs add whole branches (section 16).

### Per-skill state

| Field | Meaning |
| --- | --- |
| `state` | `not_seen` → `introduced` → `practicing` → `secure` (plus a `review_due` flag) |
| `mastery` | 0–1 estimate, an exponentially weighted average of recent outcomes (correct = 1, with help = 0.5, not yet = 0) |
| `evidence_count` | Number of observations |
| `last_seen_at` / `next_review_at` | Spaced review: once a skill is `secure`, review intervals grow (2 days, 1 week, 3 weeks), Leitner-style |

Transitions use simple, testable rules, for example `practicing` → `secure` after mastery ≥ 0.8 across at least 5 observations on at least 2 different days. Rules live in one module with unit tests. A Bayesian Knowledge Tracing model can replace them later without changing the schema.

**Video stretch level.** Per subject, a comprehension level on a 1–10 scale, the same scale `vet_video` uses to rate videos. The tutor targets one step above it. After each video, the comprehension check moves it: up after an easy success, down after he got lost, unchanged otherwise. Evidence from the screen observer counts toward skill states too, at a lower weight than skills the tutor checked directly.

### Interests

Topics the child brings up or lights up about (sharks, trains, space) with a strength score that rises on mention and decays slowly over weeks. The tutor uses the top interests to frame practice ("Let's count shark teeth").

### Session summaries

When a session ends, a background job sends the transcript and the session's observations to Claude (Sonnet) with a fixed prompt and writes two outputs:

- **Parent summary:** a short paragraph on what was explored, what went well, what was hard, and any flags.
- **Tutor notes:** two or three short lines for the next session ("Wants to finish the volcano story", "Mixing up b and d").

### What the memory never holds

Only learning-relevant observations are stored. The tutor does not record guesses about personality, behaviour or health, or details about family members beyond what parents put in house notes. Parents can edit or delete any record, and a "forget this" action removes it and anything derived from it.

### Profile assembled at session start

Name and age, house notes, the top 5 interests, up to 10 skills in `practicing` or due for review, the last 3 sessions' tutor notes, and the current video stretch level per subject. Assembly is a pure function of DB state, so it can be snapshot-tested.

## 9. Parent console

The parent console is where every decision the tutor can't make lives: what content exists, how long sessions run, what the tutor knows, and what happened today. It is a password-protected web app served by the daemon, opened on the device through the unlock gesture or from a phone on the home network.

### Screens

| Screen | What parents do there |
| --- | --- |
| Today | Live status (in session, app running, idle), time so far, open flags, latest session summary |
| Sessions | List of sessions; each opens to a full transcript with tool calls, board snapshots, videos played and apps launched, plus the parent summary |
| Progress | Skills tree coloured by state, interests, trend over weeks, "skills due for review" |
| Memory | Every observation, interest, tutor note and house note, editable and deletable, with "forget this" |
| Library | Videos: every pick with the tutor's vetting reasons and level estimate, rejected candidates, block or unblock a video or channel, channel reputation. Images: upload and tag. Pending queue from `request_content` |
| Apps | Enable or disable manifests, choose activities, set per-app time caps |
| Session control | Pause or end the current session from the console, and how readily the tutor suggests breaks. There are no time limits |
| Learner | Name, age, avatar, age profile, voice and speaking speed, tap-to-talk or hands-free |
| Settings | Model choice, STT/TTS providers, API keys (write-only fields), LAN access on or off, parent password, backup and export |

### Flags and notifications

- `flag_for_parent` calls and safety-filter hits appear on the Today screen with the transcript excerpt.
- High-severity flags can also send a push notification to the parent's phone through a self-hosted ntfy server or email (optional; your VPS could host ntfy).

### LAN access

Off by default. When on, the console listens on the LAN interface over HTTPS with a self-signed certificate, requires the parent password plus a session cookie, and rate-limits logins. The child UI endpoints are never exposed beyond `127.0.0.1`.

## 10. Safety, privacy and compliance

Safety comes from five independent layers, so a failure in one (for example the model saying something it shouldn't) is caught or contained by another. Privacy comes from keeping data local, sending providers only what each turn needs, and letting parents see and delete everything.

### Safety layers

1. **Charter:** the core system prompt (section 6), plus Anthropic's child-safety system prompt if one is offered for your account. Anthropic says it may provide one and that organizations serving minors should use it ([guidelines for organizations serving minors](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors)).
2. **Output check:** every tutor sentence passes a fast local check (a word and pattern list) before TTS. A hit replaces the sentence with a neutral redirect and raises a flag. An optional asynchronous classifier pass (Haiku) reviews each finished turn and flags, without blocking, anything off-tone or age-inappropriate.
3. **Action allowlists:** the tutor can only launch manifest apps and play videos that passed vetting; it can never type a URL. Watch-along can stop a video mid-play. Open YouTube search is still the widest door in the system (section 16).
4. **Kiosk lockdown:** section 4. No web, no shell, no file manager.
5. **Human review:** transcripts, flags and summaries in the parent console.

### Distress and disclosure handling

If the child says something suggesting fear, sadness, injury, or that someone is hurting him, the tutor answers kindly, tells him to go find a trusted grown-up now, and raises a high-severity flag. It does not probe or ask leading questions. Parents should know this is a backstop, not a monitoring system.

### What leaves the machine

| Data | Goes to | Minimised how |
| --- | --- | --- |
| Conversation text, learner summary, screen frames during apps and videos | Anthropic (Claude API) | First name only; no address, school or family surnames; house notes reviewed by the parent |
| Child's voice audio, video soundtrack during watch-along | Cloud STT provider (if chosen) | Streamed per turn only; switch to local whisper.cpp for zero audio egress |
| Tutor text | Cloud TTS provider (if chosen) | Piper default keeps this local |
| Video searches and playback | YouTube (via nocookie embed) | Privacy-enhanced domain; no Google sign-in in the kiosk browser |

Check each provider's data-retention terms before enabling it, and prefer settings that disable training on your data.

### Local data

- SQLite DB and logs in `/var/lib/schoolbook`, readable only by the `schoolbook` user.
- Raw audio is not stored by default. A parent setting keeps recordings for 7 days to help tune STT.
- Retention settings for transcripts (default: keep forever), one-click export (JSON + Markdown), and full delete.
- Encrypted nightly backup to a parent-chosen location (for example your VPS via `restic`).

### Policy and law

- **Anthropic's requirements:** products that let minors interact directly with the API must add safeguards suited to their use case, tell users they are talking to an AI and not a person, and comply with child-privacy laws such as COPPA ([same guidelines](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors); [child safety guidance for developers](https://support.claude.com/en/articles/15591275-child-safety-guidance-for-developers)). Schoolbook's design meets the first two by construction: layered safeguards, and a tutor that says it is a computer helper with a non-human avatar.
- **Family use vs. a service:** a parent running Schoolbook at home with their own API key, for their own child, is a very different position from someone offering it to other families. If Schoolbook is ever offered as a hosted service, or to other families under one operator's API key, that operator takes on COPPA duties such as verifiable parental consent and a children's privacy notice. Get legal advice before that step.
- **Design consequence:** each installation uses its own family's API keys (bring your own key), and the software is GPL and self-hosted. This keeps every family as its own operator, with data on its own machine.

## 11. Data model and configuration

All runtime state is in one SQLite database. All static policy is in YAML files under `/etc/schoolbook`, validated with Pydantic at startup. A bad config refuses to start the daemon rather than running with a guessed default.

### Database tables

| Table | Key columns |
| --- | --- |
| `learners` | id, first\_name, birth\_year, age\_profile, avatar, voice, talk\_mode, created\_at |
| `sessions` | id, learner\_id, started\_at, ended\_at, end\_reason, minutes\_used, model, parent\_summary, tutor\_notes |
| `turns` | id, session\_id, seq, role (child / tutor / event), text, stt\_confidence, created\_at |
| `tool_calls` | id, turn\_id, tool, input\_json, result\_json, allowed, latency\_ms |
| `skills` | id (dotted path), parent\_id, title, kid\_description, age\_min, age\_max, source (core / pack / parent) |
| `skill_states` | learner\_id, skill\_id, state, mastery, evidence\_count, last\_seen\_at, next\_review\_at |
| `observations` | id, learner\_id, skill\_id, session\_id, outcome, evidence, created\_at |
| `interests` | learner\_id, topic, strength, last\_mentioned\_at |
| `notes` | id, learner\_id, kind (tutor / house), text, source\_session\_id, created\_at |
| `videos` | id, source, source\_ref, title, duration\_s, start\_s, end\_s, summary, age\_min, age\_max, verdict (approved / rejected / blocked), verdict\_reasons, est\_level, vetted\_at, times\_played |
| `video_tags` / `video_skills` | video\_id, tag or skill\_id |
| `images` | id, path, title, license, tags |
| `content_requests` | id, learner\_id, kind, description, status, created\_at |
| `flags` | id, session\_id, turn\_id, severity, reason, source (tutor / output-check / classifier / observer), resolved\_at |
| `settings` | key, value\_json (parent-editable runtime settings) |
| `audit_log` | id, actor (parent / system), action, detail\_json, created\_at |

### Files on disk

```text
/etc/schoolbook/
  schoolbook.yaml        # providers, ports, limits, model choice
  secrets.env            # API keys (0600, owner schoolbook)
  chromium-policy.json   # symlinked into Chromium's managed policy dir
  apps.d/*.yaml          # app manifests
  profiles/*.yaml        # age profiles (age-6.yaml, age-9.yaml, ...)
  output-check.txt       # blocked words and patterns
/var/lib/schoolbook/
  schoolbook.db
  images/  videos/  backups/
/usr/share/schoolbook/
  ui/  console/  prompts/  skills/  sounds/
```

### Age profile (excerpt)

```yaml
id: age-6
max_sentences_per_turn: 3
max_words_per_sentence: 12
target_reading_grade: 1
talk_mode_default: tap
break_suggestions: gentle      # off | gentle | frequent; never a hard stop
video_duration_minutes: [1, 30]
video_stretch_steps: 1         # how far above the current level to aim
watch_along_pause_min_seconds: 120
observer_frame_interval_s: 3
subject_weights: {reading: 3, math: 3, science: 2, world: 2, arts: 1, cs: 1, philosophy: 1}
```

## 12. Engineering practices

Schoolbook is a GPL-3.0-or-later monorepo built test-first, versioned with Semantic Versioning, and documented in a Keep a Changelog `CHANGELOG.md`. Every phase in section 13 starts with failing tests that define its acceptance criteria.

### Repository layout

```text
schoolbook/
  LICENSE                  # GPL-3.0-or-later full text
  CHANGELOG.md             # Keep a Changelog; [Unreleased] at top
  README.md
  pyproject.toml           # uv workspace
  daemon/                  # schoolbookd (Python)
    src/schoolbookd/
      api/  tutor/  tools/  providers/{stt,llm,tts}/  learner/  content/  policy/  db/
    tests/{unit,integration,evals}/
  session/                 # schoolbook-session agent (Python)
  protocol/                # shared Pydantic message models + generated TS types
  ui/                      # child UI (React + TS + Vite)
  console/                 # parent console (React + TS + Vite)
  prompts/  skills/  profiles/  apps.d/   # shipped content
  packaging/
    debian/  systemd/  greetd/  chromium/  polkit/  install.sh
  docs/
    adr/                   # architecture decision records
```

### Test-driven development

- New behaviour starts as a failing test: pytest for Python, Vitest for the UIs, Playwright for end-to-end flows in a headless Chromium.
- Providers sit behind interfaces with fake implementations (`FakeSTT` returns scripted transcripts, `FakeLLM` replays recorded Claude responses including tool calls, `FakeTTS` returns silence of the right length), so the whole tutor loop runs in tests with no network.
- The policy layer (tool allowlists, limits, unlock) carries the strictest coverage target: every branch.
- Prompt and model behaviour has its own eval suite (section 14), run on demand and before each release, separate from the fast unit tests.

### Versioning and changelog

- SemVer `MAJOR.MINOR.PATCH`, starting at `0.1.0`. While below 1.0, minor bumps may break config; from 1.0, a config or DB schema change that needs manual action is a major bump.
- The protocol package carries its own version; the daemon refuses a UI or session agent with an incompatible major version.
- Every PR adds a line under `[Unreleased]` in `CHANGELOG.md` (Added / Changed / Deprecated / Removed / Fixed / Security). Releasing moves those lines under the new version heading with the date.
- Database migrations are Alembic revisions, run automatically on daemon start after a backup.

### Licensing

- GPL-3.0-or-later for all code, with SPDX headers on every source file, checked in CI with the `reuse` tool.
- Shipped content (prompts, skills, profiles) also GPL; bundled images keep their own open licenses, recorded in `images` table and a `NOTICE` file.
- Dependencies must be GPL-compatible; CI runs a license check on Python and npm dependencies.

### CI (GitHub Actions)

Lint and format (ruff, eslint, prettier), type checks (mypy strict, `tsc --noEmit`), unit and integration tests, Playwright end-to-end tests, `reuse lint`, dependency license check, and a `.deb` build artifact on tags. Architecture decisions go in `docs/adr/` as short numbered records (for example "ADR-0003: Chromium over Tauri for v1").

## 13. Implementation plan

Ten phases take Schoolbook from an empty repo to 1.0, each ending in a tagged release whose gate is a set of tests written at the start of the phase. The order puts the riskiest unknowns first: whether the Toughbook can run the kiosk, and whether a six-year-old's speech is recognised well enough.

1. **Phase 0 — Foundations (`0.1.0`)**
   - Monorepo, uv workspace, Vite apps, CI, `reuse`, `CHANGELOG.md`, GPL `LICENSE`, ADR template.
   - `protocol` package: Pydantic models for every WebSocket and Unix-socket message, with generated TypeScript types.
   - Config loading and validation; SQLite schema v1 with Alembic; fake STT, LLM and TTS providers.
   - **Gate:** CI green; `schoolbookd --check-config` rejects malformed configs with clear errors.
2. **Phase 1 — Kiosk spike and lockdown (`0.2.0`)**
   - On the actual Toughbook: greetd autologin, cage, session agent, Chromium kiosk with policy, parent unlock.
   - Spike questions to answer and record as ADRs: does cage show GCompris on top and return to Chromium on exit; does `grim` capture frames under cage; can PipeWire's monitor source be recorded from the session; touch screen and mic quality.
   - **Gate:** a scripted escape checklist (section 4 table) passes by hand on the Toughbook; Playwright tests cover unlock, lockout and relock.
3. **Phase 2 — Text tutor and board (`0.3.0`)**
   - Tutor loop with streaming Claude, tool dispatch and policy checks; core charter and age-6 profile; `show_board`, `ask_choice`; session logging.
   - A hidden developer text box stands in for voice.
   - **Gate:** recorded-conversation tests pass with the fake LLM; eval suite v0 (section 14) passes against the real model.
4. **Phase 3 — Voice (`0.4.0`)**
   - AudioWorklet capture, STT interface with one cloud provider and whisper.cpp, sentence chunker, Piper TTS, tap-to-talk, interruption, per-turn latency metrics.
   - Record 30–60 minutes of the child's real speech (with your consent as parent) and benchmark STT providers on it.
   - **Gate:** median end-of-speech to first audio under 1.5 s on the Toughbook (cloud STT path); word error rate on the child benchmark recorded per provider and a default chosen.
5. **Phase 4 — YouTube search, vetting and playback (`0.5.0`)**
   - `search_videos`, `vet_video` (hard filters, metadata, frame thumbnails, level estimate), verdict cache, channel reputation, block list.
   - Player with overlay controls, end-screen suppression, Chromium domain allowlist captured from real traffic.
   - Watch-along: PipeWire capture of playback audio to STT, live transcript to the tutor, `video_control`.
   - **Gate:** no YouTube UI or link reachable by touch or keyboard; vetting eval set (section 14) meets its targets; a red-team list of known-bad query terms produces zero approved videos.
6. **Phase 5 — Apps and screen observation (`0.6.0`)**
   - App manifests, launch and return, `xdg-open` stub, Home button.
   - Screen observer: frame capture, change detection, Haiku vision notes, consolidated summaries, stuck detection.
   - **Gate:** the tutor launches a GCompris activity at a level, the child plays, and on return the tutor's summary matches what happened in at least 9 of 10 scripted test plays.
7. **Phase 6 — Learner model (`0.7.0`)**
   - Skills map, observations, state rules, interests, stretch levels, post-session summary job, profile assembly.
   - **Gate:** unit tests for every state transition; profile snapshot tests; summaries reviewed by you for 10 sessions.
8. **Phase 7 — Parent console (`0.8.0`)**
   - All screens from section 9, LAN access, flags, optional ntfy push.
   - **Gate:** Playwright coverage of every console action; blocking a channel removes it from future searches immediately.
9. **Phase 8 — Hardening and packaging (`0.9.0`)**
   - Output check and classifier, backups, `.deb` and `install.sh`, systemd units, crash recovery, log rotation.
   - **Gate:** clean install on a fresh Debian 13 and Ubuntu LTS VM plus the Toughbook; an 8-hour soak test with scripted traffic and no memory growth or crashes.
10. **Phase 9 — Pilot (`1.0.0`)**
    - Two weeks of real use, with you nearby for the first sessions and reading every transcript.
    - Tune prompts, vetting thresholds, voice and pacing from what you see; fix what breaks.
    - **Gate:** you are comfortable leaving him with it; tag 1.0.

Each phase follows the same loop: write the gate tests, build until they pass, update `CHANGELOG.md`, tag the release.

## 14. Testing and evaluation

Deterministic code gets ordinary tests; model behaviour gets an eval suite with scored scenarios and pass thresholds. Both run in CI, but evals call the real API and run on demand and before every release, not on every push.

### Test layers

| Layer | Tools | Covers |
| --- | --- | --- |
| Unit | pytest, Vitest | Policy checks, learner-state rules, sentence chunker, config validation, profile assembly, vetting hard filters |
| Integration | pytest with fake providers | Full tutor loop: scripted child turns in, expected tool calls and events out; WebSocket protocol; DB migrations |
| End-to-end | Playwright in headless Chromium | Child UI flows, unlock, video overlay, console actions |
| Hardware | Manual checklist on the Toughbook each release | Escape checklist, mic, touch, audio capture, observer capture |
| Soak | Scripted traffic for 8 hours | Leaks, crash recovery, log growth |

### Eval suites (real model)

| Suite | What it checks | Pass threshold (initial) |
| --- | --- | --- |
| Kid-speak | 100 child prompts across subjects; readability of replies, sentence length, one question per turn, no markdown | ≥ 95% of turns within the age-6 limits |
| Pedagogy | Scripted practice exchanges; uses the hint ladder rather than giving answers; follows the child's topic changes | ≥ 90% judged correct by a rubric grader, spot-checked by you |
| Safety | Hard topics, distress statements, requests for secrets or personal info, jailbreak attempts phrased as a kid would | 100% safe handling; every distress case raises a flag |
| Tool discipline | Requests to open websites, unlisted apps, or play unvetted videos | 0 policy-violating calls reach execution; ideally the model never attempts them |
| Video vetting | A labelled set of 300+ real YouTube videos: good, too hard, too easy, kid-bait, inappropriate | 0 inappropriate approvals; ≥ 85% agreement with your labels on suitability and level |
| Observation | Recorded GCompris and video sessions with known outcomes | Summary matches the outcome in ≥ 90% of cases |

Rubric grading uses a separate Claude call with a fixed rubric; you review a sample by hand every release. Failed cases become regression cases. Eval results are stored per release so prompt or model changes can be compared.

## 15. Deployment

The reference install is current Debian stable or Ubuntu LTS on the Toughbook, set up by one script that creates the users, installs packages and configs, and asks the parent for a password and API keys. Any x86-64 Linux machine with a mic, speakers and a Wayland-capable GPU should work the same way.

### Hardware check (Toughbook first)

- **Model and specs:** Toughbook models vary widely (CF-31, CF-54, CF-33, FZ-55 and others). Record CPU, RAM, GPU, screen resolution and whether it has a touch screen. 8 GB RAM is comfortable; 4 GB works with cloud STT and Piper.
- **Audio:** built-in mics on rugged laptops are often mediocre and far from the child. A cheap USB headset or a desk mic can fix STT accuracy more than any provider change; test in Phase 3.
- **Touch:** if present, the UI is designed touch-first (buttons at least 64 px); otherwise a mouse plus the space bar for talking.
- **Firmware:** set a BIOS supervisor password, disable boot from USB and network, internal disk first.

### Install steps

1. Install the OS with a normal admin (parent) account; enable unattended security upgrades.
2. Clone the repo or install the `.deb`; run `sudo ./install.sh`.
3. The script installs dependencies (`greetd`, `cage`, `chromium`, `grim`, `pipewire`, Piper and its voice, `whisper.cpp` if chosen, GCompris and the seed apps), creates the `kid` and `schoolbook` users, writes systemd units, greetd config, Chromium policy, polkit rules, sysctl and logind settings.
4. It prompts for the parent password, the child's first name and age, the Anthropic API key, the YouTube Data API key, and STT/TTS choices.
5. It runs `schoolbookd --check-config`, a self-test (mic level, TTS sample, one Claude call, one YouTube search), then reboots into the kiosk.

### Updates and backup

- New releases ship as `.deb` packages; the parent console shows when an update is available, and the parent installs it from the admin account (no self-updating code).
- Nightly encrypted backup of `/var/lib/schoolbook` with `restic` to a parent-chosen target, for example your VPS.
- Uninstall removes the kiosk config and users, leaving the data directory unless the parent asks for it to go.

### Other machines

The same package and script target any Debian or Ubuntu derivative. Fedora and Arch packages come after 1.0. Machines whose GPU misbehaves under Wayland use the Xorg + Openbox fallback session, chosen at install time.

## 16. Extensibility, open decisions and risks

Growing beyond one six-year-old is mostly configuration: new age profiles, new skills branches, new app manifests and new providers, all loaded from files. Each extension point below is an interface or a file format in v1, even where only one implementation ships.

### Extension points

| Extension | How it plugs in | Example |
| --- | --- | --- |
| More learners | `learners` table, picture-button login, per-learner memory | Siblings sharing one laptop |
| Age profiles | `profiles/*.yaml` | `age-9`: longer turns, reading on screen, typed answers |
| Curriculum packs | Skills YAML + matching app manifests | Chess, music theory, Spanish, early programming |
| Tools | Python entry points registering a tool schema and handler, gated by policy | Handwriting canvas, drawing critique, chess board |
| Providers | STT, LLM, TTS interfaces | A local LLM for offline use, a new TTS voice |
| Content sources | Video source interface | PeerTube instances, a home media folder |
| Languages | UI strings and prompts per locale; multilingual STT/TTS | Spanish-language sessions |
| Input | Handwriting and drawing on touch screens; an opt-in camera to show the tutor objects | "Look what I built!" |

### Open decisions

| Decision | Options | Decide by |
| --- | --- | --- |
| Cloud vs local STT default | Cloud for accuracy vs whisper.cpp for privacy and zero cost | Phase 3 benchmark |
| Haiku vs Sonnet for the main tutor | Speed vs depth; can switch per learner | Phase 2 evals and pilot |
| Speaking over apps when stuck | On (default) vs off | Pilot |
| Transcript pre-check for videos | Third-party transcripts (terms risk) vs watch-along only | After Phase 4 vetting evals |
| Disk encryption | TPM unlock, partial encryption, none | Phase 1, depends on Toughbook TPM |
| Push notifications | Self-hosted ntfy, email, none | Phase 7 |

### Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Open YouTube search surfaces something harmful that passes vetting (disturbing content disguised as kids' videos is a known problem) | Medium | High | Five-stage vetting, watch-along stop, channel reputation, block list, full log; consider a supervised first month where you skim every pick daily |
| Child's speech poorly recognised | Medium | High | Benchmark on his real speech; better mic; tap-to-talk; tutor confirms when unsure |
| API costs with no time limit and frequent vision calls | Medium | Medium | Change-detection on frames, Haiku for vision, prompt caching; a monthly spend figure and alert in the console (a cost alert, not a time limit) |
| Long unlimited sessions crowd out other play | Low–medium | Medium | Tutor suggests movement and off-screen missions; time-so-far visible on the console's Today screen |
| Kiosk escape found by a curious kid | Medium | Low | Layered lockdown; escape attempts are harmless (no web, no shell) and logged |
| Cage or the Toughbook GPU can't do what the design assumes (app stacking, screencopy) | Medium | Medium | Phase 1 spike first; Xorg + Openbox fallback |
| YouTube changes embed behaviour or API quota | Low | Medium | Overlay player isolates the UI; local files as a second source |
| Tutor slides into adult register or long monologues over long sessions | Medium | Medium | Kid-speak evals; per-turn length limits enforced in the sentence chunker as a backstop |
