# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Wire the tutor loop to the database and the allowlists."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from schoolbookd.content.apps import AppManifest, build_argv
from schoolbookd.db.models import Video
from schoolbookd.db.store import Store
from schoolbookd.learner.memory import assemble_profile
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.policy.tools import PolicyContext, ToolPolicy
from schoolbookd.providers.base import LLMProvider, TTSProvider
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
                app_id: {item.id for item in manifest.activities}
                for app_id, manifest in self.apps.items()
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
            llm=self.llm,
            policy=ToolPolicy(),
            execute=lambda name, args: self._execute(live, name, args),
            output_check=self.output_check,
            model=self.model,
            max_sentences=self.age_profile.max_sentences_per_turn,
            max_words=self.age_profile.max_words_per_sentence,
        )
        outcome = loop.run_turn(
            text,
            system=system,
            history=live.history,
            policy_context=self.policy_context(live),
        )
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
            self.store.add_flag(
                session_id=live.session_id,
                turn_id=child_turn,
                severity="high" if "distress" in outcome.flag_reason else "medium",
                reason=outcome.flag_reason or "flagged",
                source="tutor" if "distress" not in outcome.flag_reason else "output-check",
                excerpt=text,
            )
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
            parent_summary = response.text or fallback
            tutor_notes = response.text
        self.store.end_session(live.session_id, reason, parent_summary, tutor_notes)

    def _age_text(self) -> str:
        from schoolbookd.tutor.prompts import render_age_profile

        return render_age_profile(self.age_profile)

    def _execute(self, live: LiveState, name: str, args: dict[str, object]) -> dict[str, object]:
        if name == "show_board":
            live.screen = "board"
            return {"shown": True}
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
            return {"flagged": True}
        if name == "request_content":
            request_id = self.store.request_content(
                live.learner_id, str(args["kind"]), str(args["description"])
            )
            return {"request_id": request_id, "fetched": False}
        if name == "launch_app":
            manifest = self.apps[str(args["app_id"])]
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
            if action == "stop":
                live.playing_video = None
                live.screen = "home"
            return {"action": action}
        if name == "get_observations":
            notes = live.observations
            live.observations = []
            return {"notes": notes}
        if name == "suggest_break":
            return {"suggested": True}
        if name == "end_session":
            return {"ending": True}
        if name == "search_videos":
            return {"candidates": []}
        if name == "vet_video":
            return {"verdict": "unknown"}
        return {"error": "not implemented"}

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
