# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Wire the tutor loop to the database and the allowlists."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from schoolbookd.content.apps import AppManifest, build_argv
from schoolbookd.content.catalog import VideoCatalog
from schoolbookd.content.pictures import PictureMaker, picture_id, picture_prompt
from schoolbookd.db.models import ImageRow, Video
from schoolbookd.content.playback import pause_allowed, split_summary
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
    model: str = "fake"
    summary: LLMProvider | None = None
    catalog: VideoCatalog | None = None
    classifier: KeywordClassifier | None = None
    notifier: Notifier | None = None
    min_video_pause_s: float = 120
    pictures: PictureMaker | None = None
    images_dir: Path | None = None

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
            self._age_text(),
            assemble_profile(learner),
            state,
        )
        loop = TutorLoop(
            llm=_LoggingLLM(self.llm, self.store, live.session_id),
            policy=ToolPolicy(),
            execute=lambda name, args: self._execute(live, name, args),
            output_check=self.output_check,
            model=self.model,
            max_sentences=self.age_profile.max_sentences_per_turn,
            max_words=self.age_profile.max_words_per_sentence,
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

    def _age_text(self) -> str:
        from schoolbookd.tutor.prompts import render_age_profile

        return render_age_profile(self.age_profile)

    def run_tool(self, live: LiveState, name: str, args: dict[str, object]) -> dict[str, object]:
        decision = ToolPolicy().check(name, args, self.policy_context(live))
        if not decision.allowed:
            return {"error": decision.reason}
        return self._execute(live, name, args)

    def _execute(self, live: LiveState, name: str, args: dict[str, object]) -> dict[str, object]:
        if name == "show_board":
            live.screen = "board"
            return {"shown": True}
        if name == "show_picture":
            if self.pictures is None or self.images_dir is None:
                return {"error": "pictures are not ready"}
            topic = str(args["topic"]).strip()
            image_id = picture_id(topic)
            self.images_dir.mkdir(parents=True, exist_ok=True)
            path = self.images_dir / f"{image_id}.png"
            if not path.is_file():
                path.write_bytes(self.pictures.generate(picture_prompt(topic)))
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
            live.screen = "app"
            return {"argv": argv, "app_id": manifest.id}
        if name == "list_apps":
            return {"apps": sorted(self.apps)}
        if name == "get_skill_status":
            profile = self.store.profile_input(live.learner_id)
            return {"practicing": profile.practicing, "review_due": profile.review_due}
        if name == "play_video":
            live.playing_video = str(args["video_id"])
            live.screen = "video"
            video = self.store.video(live.playing_video)
            if video is not None:
                video.times_played += 1
                self.store.save_video(video)
            return {"playing": live.playing_video}
        if name == "video_control":
            action = str(args.get("action"))
            if action == "pause" and not pause_allowed(
                live.last_video_pause_at, live.now_s, self.min_video_pause_s
            ):
                return {"action": "pause", "deferred": True}
            if action == "pause":
                live.last_video_pause_at = live.now_s
            if action == "stop":
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
            return {"candidates": self.catalog.search(str(args["query"]))}
        if name == "vet_video":
            if self.catalog is None:
                return {"verdict": "unknown"}
            return self.catalog.vet(str(args["video_id"]))
        return {"error": "not implemented"}

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
