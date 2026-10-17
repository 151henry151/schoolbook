# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Wire the tutor loop to the database and the allowlists."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from schoolbookd.content.apps import AppManifest, build_argv
from schoolbookd.content.catalog import VideoCatalog
from schoolbookd.content.pictures import (
    PictureMaker,
    looks_prompt,
    picture_id,
    picture_prompt,
    picture_suffix,
)
from schoolbookd.content.playback import pause_allowed, split_summary
from schoolbookd.db.models import ImageRow, Video
from schoolbookd.db.store import Store
from schoolbookd.learner.memory import assemble_profile
from schoolbookd.notify import Notifier
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.policy.tools import PolicyContext, ToolPolicy
from schoolbookd.providers.base import LLMProvider, LLMRequest, LLMResponse, TTSProvider
from schoolbookd.safety.classifier import KeywordClassifier
from schoolbookd.tutor.loop import TurnOutcome, TutorLoop
from schoolbookd.tutor.prompts import AgeProfile, assemble_prompt


@dataclass
class LiveState:
    session_id: str
    learner_id: str
    history: list[dict[str, object]] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    playing_video: str | None = None
    playing_audio_only: bool = False
    song_recorded: bool = False
    video_recorded: bool = False
    song_queue: list[str] = field(default_factory=list)
    app_pid: int | None = None
    paused: bool = False
    screen: str = "home"
    last_video_pause_at: float | None = None
    now_s: float = 0.0


@dataclass
class Runtime:
    store: Store
    llm: LLMProvider
    tts: TTSProvider
    output_check: OutputCheck
    apps: dict[str, AppManifest]
    age_profile: AgeProfile
    core_prompt: str
    age_profiles: dict[str, AgeProfile] = field(default_factory=dict)
    model: str = "fake"
    summary: LLMProvider | None = None
    catalog: VideoCatalog | None = None
    classifier: KeywordClassifier | None = None
    notifier: Notifier | None = None
    min_video_pause_s: float = 120
    pictures: PictureMaker | None = None
    scenes: PictureMaker | None = None
    images_dir: Path | None = None
    launcher: Callable[[list[str]], int] | None = None
    killer: Callable[[int], None] | None = None
    app_running: Callable[[int], bool] | None = None
    overlay: Callable[[Callable[[], None]], Callable[[], None]] | None = None
    on_app_exit: Callable[[], None] | None = None
    _hide_overlay: Callable[[], None] | None = field(default=None, init=False, repr=False)

    def profile_for(self, learner_id: str) -> AgeProfile:
        learner = self.store.learner(learner_id)
        return self.age_profiles.get(learner.age_profile, self.age_profile) if learner else self.age_profile

    def catalog_for(self, live: LiveState) -> VideoCatalog | None:
        return self.catalog.for_profile(self.profile_for(live.learner_id)) if self.catalog else None

    def image_path(self, image_id: str) -> Path | None:
        if not image_id or "/" in image_id or ".." in image_id:
            return None
        if self.images_dir is not None:
            for suffix in (".png", ".webp", ".jpg", ".jpeg", ".svg"):
                path = self.images_dir / f"{image_id}{suffix}"
                if path.is_file():
                    return path
        with self.store.session() as db:
            row = db.get(ImageRow, image_id)
        if row is None:
            return None
        path = Path(row.path)
        return path if path.is_file() else None

    def finish_picture(
        self,
        live: LiveState,
        topic: str,
        image_id: str,
        *,
        kind: str = "diagram",
    ) -> dict[str, object]:
        maker = self._picture_maker(kind)
        if maker is None or self.images_dir is None:
            return {"error": "pictures are not ready"}
        self.images_dir.mkdir(parents=True, exist_ok=True)
        path = self.image_path(image_id)
        if path is None:
            path = self._save_picture(image_id, maker.generate(self._picture_prompt(kind, topic, live.learner_id)))
        self.store.add_image(image_id, str(path), topic, "generated", "generated")
        live.screen = "board"
        return {"shown": True, "image_id": image_id}

    def _picture_maker(self, kind: str) -> PictureMaker | None:
        if kind == "looks":
            return self.scenes or self.pictures
        return self.pictures or self.scenes

    def _picture_prompt(self, kind: str, brief: str, learner_id: str) -> str:
        if kind == "looks":
            return looks_prompt(brief, self.profile_for(learner_id).age_years)
        return picture_prompt(brief, self.profile_for(learner_id).age_years)

    def _save_picture(self, image_id: str, data: bytes) -> Path:
        assert self.images_dir is not None
        path = self.images_dir / f"{image_id}{picture_suffix(data)}"
        path.write_bytes(data)
        return path

    def policy_context(self, live: LiveState) -> PolicyContext:
        disabled = self.store.get_setting("disabled_apps", [])
        disabled_ids = set(disabled) if isinstance(disabled, list) else set()
        enabled = {app_id for app_id in self.apps if app_id not in disabled_ids}
        return PolicyContext(
            skills=self.store.skill_ids(),
            image_ids=self.store.image_ids(),
            approved_videos=self.store.approved_ids(),
            blocked_videos=self.store.blocked_ids(),
            enabled_apps=enabled,
            app_activities={
                app_id: {item.id for item in manifest.activities} for app_id, manifest in self.apps.items()
            },
            playing_video=live.playing_video,
        )

    def child_turn(self, live: LiveState, text: str) -> TurnOutcome:
        if live.paused:
            return TurnOutcome(["The session is paused."], [], False, "", False, False)
        learner = self.store.profile_input(live.learner_id)
        elapsed = "session in progress"
        state = "\n".join(
            [
                f"Elapsed: {elapsed}.",
                f"On screen: {live.screen}.",
                f"Video: {live.playing_video or 'none'}.",
                "Observations: " + ("; ".join(live.observations[-5:]) or "none") + ".",
            ]
        )
        system = assemble_prompt(
            self.core_prompt,
            self._age_text(live.learner_id),
            assemble_profile(learner),
            state,
        )
        loop = TutorLoop(
            llm=_LoggingLLM(self.llm, self.store, live.session_id),
            policy=ToolPolicy(),
            execute=lambda name, args: self._execute(live, name, args),
            output_check=self.output_check,
            model=self.model,
            max_sentences=self.profile_for(live.learner_id).max_sentences_per_turn,
            max_words=self.profile_for(live.learner_id).max_words_per_sentence,
        )
        try:
            outcome = loop.run_turn(
                text,
                system=system,
                history=live.history,
                policy_context=self.policy_context(live),
            )
        except Exception:
            live.screen = "offline"
            return TurnOutcome(["The tutor is resting."], [], False, "", False, False)
        child_turn = self.store.add_turn(live.session_id, "child", text)
        tutor_text = " ".join(outcome.sentences)
        tutor_turn = self.store.add_turn(live.session_id, "tutor", tutor_text)
        for record in outcome.tool_calls:
            self.store.add_tool_call(
                tutor_turn,
                record.name,
                record.arguments,
                record.result,
                allowed=record.allowed,
            )
        if outcome.flagged:
            severity = "high" if "distress" in outcome.flag_reason else "medium"
            self.store.add_flag(
                session_id=live.session_id,
                turn_id=child_turn,
                severity=severity,
                reason=outcome.flag_reason or "flagged",
                source="tutor" if "distress" not in outcome.flag_reason else "output-check",
                excerpt=text,
            )
            if severity == "high":
                self._alert(outcome.flag_reason or "distress")
        if self.classifier is not None and tutor_text:
            tone = self.classifier.review(tutor_text)
            if tone:
                self.store.add_flag(
                    session_id=live.session_id,
                    turn_id=tutor_turn,
                    severity="medium",
                    reason=tone,
                    source="classifier",
                    excerpt=tutor_text,
                )
        calls = self.store.get_setting("model_calls", 0)
        self.store.put_setting("model_calls", int(calls) + 1 if isinstance(calls, int) else 1, actor="system")
        if outcome.redirected:
            self.store.add_flag(
                session_id=live.session_id,
                turn_id=tutor_turn,
                severity="medium",
                reason="output check replaced a sentence",
                source="output-check",
                excerpt=tutor_text,
            )
        live.history.append({"role": "user", "content": text})
        live.history.append({"role": "assistant", "content": tutor_text})
        if outcome.ended:
            self._finish(live, "child", " ".join(outcome.sentences))
        return outcome

    def speak(self, text: str) -> bytes:
        return self.tts.synthesize(text)

    def start_app(self, argv: list[str]) -> int:
        if self.launcher is None:
            return 0
        return int(self.launcher(argv))

    def stop_app(self, live: LiveState, *, notify: bool = True) -> None:
        pid = live.app_pid
        hide = self._hide_overlay
        if pid is None and hide is None:
            return
        live.app_pid = None
        live.screen = "home"
        self._hide_overlay = None
        if pid is not None:
            self.kill_app(pid)
        if hide is not None:
            hide()
        if notify and self.on_app_exit is not None:
            self.on_app_exit()

    def check_app_exit(self, live: LiveState) -> None:
        if (live.app_pid is not None and self.app_running is not None
                and not self.app_running(live.app_pid)):
            self.stop_app(live)

    def kill_app(self, pid: int) -> None:
        if self.killer is not None:
            self.killer(pid)
            return
        import contextlib
        import os
        import signal

        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.kill(pid, signal.SIGTERM)

    def _gcompris_games(self, subject: str = "") -> list[dict[str, str]]:
        needle = subject.strip().lower()
        games: list[dict[str, str]] = []
        for manifest in self.apps.values():
            if manifest.id != "gcompris":
                continue
            for activity in manifest.activities:
                haystack = " ".join([
                    activity.id, activity.title, activity.description, *activity.skills,
                ]).lower()
                if needle and needle not in haystack:
                    continue
                games.append(
                    {
                        "app_id": manifest.id,
                        "activity": activity.id,
                        "title": activity.title,
                        "description": activity.description,
                        "suggested_ages": ", ".join(str(age) for age in activity.ages),
                    }
                )
        return games

    def end_from_parent(self, live: LiveState) -> None:
        self._finish(live, "parent", "The parent ended the session.")

    def _finish(self, live: LiveState, reason: str, fallback: str) -> None:
        parent_summary, tutor_notes = fallback, ""
        if self.summary is not None:
            from schoolbookd.providers.base import LLMRequest

            response = self.summary.complete(
                LLMRequest(
                    model=self.model,
                    system=[],
                    messages=[
                        {
                            "role": "user",
                            "content": "Summarize for a parent and add tutor notes.\n"
                            + json.dumps(live.history),
                        }
                    ],
                )
            )
            parent_summary, tutor_notes = split_summary(response.text or fallback)
        self.store.end_session(live.session_id, reason, parent_summary, tutor_notes)

    def _age_text(self, learner_id: str) -> str:
        from schoolbookd.tutor.prompts import render_age_profile

        return render_age_profile(self.profile_for(learner_id))

    def run_tool(
        self,
        live: LiveState,
        name: str,
        args: dict[str, object],
        *,
        defer_pictures: bool = False,
    ) -> dict[str, object]:
        decision = ToolPolicy().check(name, args, self.policy_context(live))
        if not decision.allowed:
            return {"error": decision.reason}
        return self._execute(live, name, args, defer_pictures=defer_pictures)

    def _execute(
        self,
        live: LiveState,
        name: str,
        args: dict[str, object],
        *,
        defer_pictures: bool = False,
    ) -> dict[str, object]:
        if name == "show_board":
            live.screen = "board"
            return {"shown": True}
        if name == "show_picture":
            kind = str(args.get("kind") or "diagram")
            maker = self._picture_maker(kind)
            if maker is None or self.images_dir is None:
                return {"error": "pictures are not ready"}
            topic = str(args.get("topic") or args.get("brief") or "").strip()
            brief = str(args.get("brief") or topic).strip()
            age = self.profile_for(live.learner_id).age_years
            image_id = picture_id(topic, brief if age == 6 else f"age {age}: {brief}")
            self.images_dir.mkdir(parents=True, exist_ok=True)
            path = self.image_path(image_id)
            if path is None and defer_pictures:
                return {
                    "loading": True,
                    "image_id": image_id,
                    "topic": topic,
                    "brief": brief,
                    "kind": kind,
                }
            if path is None:
                path = self._save_picture(image_id, maker.generate(self._picture_prompt(kind, brief, live.learner_id)))
            self.store.add_image(image_id, str(path), topic, "generated", "generated")
            live.screen = "board"
            return {"shown": True, "image_id": image_id}
        if name == "ask_choice":
            return {"waiting": True}
        if name == "record_observation":
            snapshot = self.store.record_observation(
                learner_id=live.learner_id,
                skill_id=str(args["skill_id"]),
                session_id=live.session_id,
                outcome=str(args["outcome"]),
                evidence=str(args.get("evidence", "")),
            )
            return {"state": snapshot.state, "mastery": snapshot.mastery}
        if name == "note_interest":
            strength = args["strength"]
            if isinstance(strength, bool) or not isinstance(strength, (int, float)):
                return {"error": "strength must be a number"}
            self.store.note_interest(live.learner_id, str(args["topic"]), float(strength))
            return {"stored": True}
        if name == "note_for_next_time":
            self.store.add_note(live.learner_id, "tutor", str(args["text"]), live.session_id)
            return {"stored": True}
        if name == "flag_for_parent":
            severity = str(args.get("severity", "low"))
            reason = str(args.get("reason", ""))
            self.store.add_flag(
                session_id=live.session_id,
                turn_id=None,
                severity=severity,
                reason=reason,
                source="tutor",
            )
            if severity == "high":
                self._alert(reason)
            return {"flagged": True}
        if name == "request_content":
            request_id = self.store.request_content(
                live.learner_id, str(args["kind"]), str(args["description"])
            )
            return {"request_id": request_id, "fetched": False}
        if name == "launch_app":
            app_id = str(args["app_id"])
            if self._cap_reached(app_id):
                return {"error": "app time cap reached"}
            manifest = self.apps[app_id]
            activity = args.get("activity")
            activity_id = activity if isinstance(activity, str) else None
            argv = build_argv(manifest, activity_id)
            self.stop_app(live, notify=False)
            try:
                pid = self.start_app(argv)
            except OSError:
                return {"error": "The game could not start. Ask a grown-up to check its installation."}
            live.screen = "app"
            live.app_pid = pid or None
            if self.overlay is not None:
                self._hide_overlay = self.overlay(lambda: self.stop_app(live))
            return {
                "argv": argv,
                "app_id": manifest.id,
                "activity": activity_id,
                "pid": pid,
            }
        if name == "list_apps":
            subject = str(args.get("subject") or "")
            games = self._gcompris_games(subject)
            if subject and not games:
                games = self._gcompris_games("")
            return {"apps": sorted(self.apps), "games": games}
        if name == "get_skill_status":
            profile = self.store.profile_input(live.learner_id)
            return {"practicing": profile.practicing, "review_due": profile.review_due}
        if name == "find_album":
            if self.catalog is None:
                return {"error": "Album lookup is unavailable."}
            return self.catalog.find_album(str(args["title"]), str(args["artist"]))
        if name == "play_album":
            songs = self.catalog.album_tracks(str(args["album_id"])) if self.catalog else []
            if not songs:
                return {"error": "Find and verify the album first. Do not invent a track list."}
            policy = ToolPolicy()
            context = self.policy_context(live)
            if any(not policy.check("play_video", {"video_id": song}, context).allowed for song in songs):
                return {"error": "An album track is blocked or unavailable. Cannot play the complete album."}
            first, *remaining = songs
            result = self.run_tool(live, "play_video", {"video_id": first, "audio_only": True})
            if "error" not in result:
                live.song_queue = remaining
            return {**result, "track_count": len(songs)}
        if name == "play_music":
            songs = self.store.familiar_songs(live.learner_id)
            if not songs:
                return {"empty": True, "message": "No familiar songs yet. Ask which song to play."}
            import random

            random.shuffle(songs)
            first, *remaining = songs
            result = self.run_tool(live, "play_video", {"video_id": first, "audio_only": True})
            if "error" not in result:
                live.song_queue = remaining
            return result
        if name == "play_video":
            catalog = self.catalog_for(live)
            if not args.get("audio_only") and catalog and not catalog.playable(str(args["video_id"])):
                return {"error": "Choose a video that fits this learner's age profile and duration window."}
            live.song_queue.clear()
            live.song_recorded = False
            live.video_recorded = False
            live.playing_audio_only = bool(args.get("audio_only"))
            live.playing_video = str(args["video_id"])
            live.screen = "video"
            video = self.store.video(live.playing_video)
            if video is not None:
                video.times_played += 1
                self.store.save_video(video)
            return {"playing": live.playing_video, "audio_only": bool(args.get("audio_only"))}
        if name == "video_control":
            action = str(args.get("action"))
            if action == "pause" and not pause_allowed(
                live.last_video_pause_at, live.now_s, self.min_video_pause_s
            ):
                return {"action": "pause", "deferred": True}
            if action == "pause":
                live.last_video_pause_at = live.now_s
            if action == "stop":
                live.song_queue.clear()
                live.playing_video = None
                live.screen = "home"
            return {"action": action, "deferred": False}
        if name == "get_observations":
            notes = live.observations
            live.observations = []
            return {"notes": notes}
        if name == "suggest_break":
            return {"suggested": True}
        if name == "end_session":
            return {"ending": True}
        if name == "search_videos":
            if self.catalog is None:
                return {"candidates": []}
            kind = str(args.get("kind") or "video")
            catalog = self.catalog_for(live)
            assert catalog is not None
            candidates = catalog.search(str(args["query"]), kind=kind)
            if kind == "video":
                history = {row["video_id"]: row for row in self.store.video_history(
                    live.learner_id, video_ids=[str(v["video_id"]) for v in candidates],
                    limit=len(candidates),
                )}
                candidates = [{**v, "watch_count": history.get(v["video_id"], {}).get("watch_count", 0),
                               "last_watched_at": history.get(v["video_id"], {}).get("last_watched_at")}
                              for v in candidates]
                # A preference, never an exclusion: all relevant candidates remain selectable.
                candidates.sort(key=lambda v: (int(str(v["watch_count"])),
                                               str(v["last_watched_at"] or "")))
            return {"candidates": candidates}
        if name == "get_video_history":
            return {"videos": self.store.video_history(live.learner_id),
                    "definition": "Watched at least 50% of the video; songs are separate."}
        if name == "set_tutor_name":
            from schoolbookd.providers.openai_realtime import normalize_tutor_name

            chosen = normalize_tutor_name(str(args.get("name", "")))
            if not chosen:
                return {"error": "name must be a short first name"}
            self.store.put_setting("tutor_name", chosen, actor="tutor")
            return {"name": chosen, "update_instructions": True}
        if name == "vet_video":
            if self.catalog is None:
                return {"verdict": "unknown"}
            catalog = self.catalog_for(live)
            assert catalog is not None
            return catalog.vet(str(args["video_id"]))
        return {"error": "not implemented"}

    def song_started(self, live: LiveState, video_id: str) -> None:
        if live.playing_audio_only and live.playing_video == video_id and not live.song_recorded:
            self.store.record_song_play(live.learner_id, video_id)
            live.song_recorded = True

    def video_watched(self, live: LiveState, video_id: str, watched_s: float, duration_s: float) -> None:
        if live.playing_audio_only or live.playing_video != video_id or live.video_recorded:
            return
        video = self.store.video(video_id)
        if video is None or duration_s <= 0 or watched_s < duration_s / 2:
            return
        # Check against the API duration too, allowing its rounding and minor player differences.
        if video.duration_s > 0 and abs(duration_s - video.duration_s) > max(5, video.duration_s * 0.02):
            return
        self.store.record_video_watch(live.learner_id, video_id)
        live.video_recorded = True

    def next_song(self, live: LiveState) -> dict[str, object] | None:
        while live.song_queue:
            video_id, *remaining = live.song_queue
            result = self.run_tool(live, "play_video", {"video_id": video_id, "audio_only": True})
            live.song_queue = remaining
            if "error" not in result:
                return result
        return None

    def _cap_reached(self, app_id: str) -> bool:
        caps = self.store.get_setting("app_caps", {})
        used = self.store.get_setting("app_minutes", {})
        if not isinstance(caps, dict) or app_id not in caps:
            return False
        so_far = used.get(app_id, 0) if isinstance(used, dict) else 0
        return int(str(so_far)) >= int(str(caps[app_id]))

    def _alert(self, reason: str) -> None:
        if self.notifier is not None:
            self.notifier.send("Schoolbook flag", reason)

    def approve_video(self, video_id: str, title: str, channel_id: str, level: int) -> None:
        self.store.save_video(
            Video(
                id=video_id,
                source="youtube",
                source_ref=video_id,
                title=title,
                channel_id=channel_id,
                verdict="approved",
                est_level=level,
                vetted_at=datetime.now(UTC),
                duration_s=300,
            )
        )


class _LoggingLLM:
    def __init__(self, inner: LLMProvider, store: Store, session_id: str) -> None:
        self._inner = inner
        self._store = store
        self._session_id = session_id

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = self._inner.complete(request)
        self._store.log_exchange(
            self._session_id,
            json.dumps({"model": request.model, "messages": len(request.messages)}),
            json.dumps({"text": response.text, "tools": [call.name for call in response.tool_calls]}),
        )
        return response
