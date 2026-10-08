# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Decide whether a tutor tool call may run. Every branch is tested."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from schoolbook_protocol.board import Board, Objects
from schoolbook_protocol.messages import ChoiceOption


@dataclass
class Decision:
    allowed: bool
    reason: str


@dataclass
class PolicyContext:
    skills: set[str] = field(default_factory=set)
    image_ids: set[str] = field(default_factory=set)
    approved_videos: set[str] = field(default_factory=set)
    blocked_videos: set[str] = field(default_factory=set)
    enabled_apps: set[str] = field(default_factory=set)
    app_activities: dict[str, set[str]] = field(default_factory=dict)
    playing_video: str | None = None
    tool_calls_used: int = 0
    max_tool_calls: int = 6


_OUTCOMES = {"correct", "with_help", "not_yet"}
_SEVERITIES = {"low", "medium", "high"}
_KINDS = {"app", "media", "image"}
_CONTROLS = {"pause", "resume", "seek", "stop"}
_KNOWN = {
    "show_board",
    "ask_choice",
    "search_videos",
    "play_video",
    "vet_video",
    "video_control",
    "show_picture",
    "switch_voice",
    "set_tutor_name",
    "list_apps",
    "launch_app",
    "get_skill_status",
    "record_observation",
    "note_interest",
    "note_for_next_time",
    "request_content",
    "flag_for_parent",
    "suggest_break",
    "end_session",
    "get_observations",
}


class ToolPolicy:
    def check(self, name: str, args: dict[str, object], ctx: PolicyContext) -> Decision:
        if name not in _KNOWN:
            return Decision(False, f"unknown tool {name}")
        if ctx.tool_calls_used >= ctx.max_tool_calls:
            return Decision(False, "tool call limit reached")
        handler = getattr(self, f"_check_{name}")
        decision: Decision = handler(args, ctx)
        return decision

    def _check_show_board(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        try:
            board = Board.model_validate({"elements": args.get("elements", [])})
        except ValidationError as exc:
            return Decision(False, exc.errors()[0]["msg"])
        for element in board.elements:
            if element.type == "image" and element.image_id not in ctx.image_ids:
                return Decision(False, "image is not in the local library")
            if isinstance(element, Objects) and element.image_id and element.image_id not in ctx.image_ids:
                return Decision(False, "image is not in the local library")
        return Decision(True, "ok")

    def _check_ask_choice(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        options = args.get("options")
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 80:
            return Decision(False, "choice prompt must be a short sentence")
        if not isinstance(options, list) or not 2 <= len(options) <= 4:
            return Decision(False, "choices need 2 to 4 options")
        for option in options:
            if not isinstance(option, dict):
                return Decision(False, "each option needs an id and a label")
            try:
                ChoiceOption.model_validate(option)
            except ValidationError:
                return Decision(False, "option labels must stay short")
        return Decision(True, "ok")

    def _check_search_videos(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 120:
            return Decision(False, "search query must be short text")
        subject = args.get("subject")
        if subject is not None and (not isinstance(subject, str) or len(subject) > 40):
            return Decision(False, "subject must be short text")
        return Decision(True, "ok")

    def _check_play_video(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        video_id = args.get("video_id")
        if not isinstance(video_id, str) or not video_id:
            return Decision(False, "video_id is required")
        if video_id in ctx.blocked_videos:
            return Decision(False, "video is blocked")
        if video_id not in ctx.approved_videos:
            return Decision(False, "video has not passed vetting")
        return Decision(True, "ok")

    def _check_vet_video(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        video_id = args.get("video_id")
        if not isinstance(video_id, str) or not video_id.strip():
            return Decision(False, "video_id is required")
        return Decision(True, "ok")

    def _check_show_picture(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        topic = args.get("topic")
        if not isinstance(topic, str) or not topic.strip() or len(topic) > 80:
            return Decision(False, "picture topic must be a short phrase")
        brief = args.get("brief", topic)
        if not isinstance(brief, str) or not brief.strip() or len(brief) > 1200:
            return Decision(False, "picture brief must be short directions")
        return Decision(True, "ok")

    def _check_switch_voice(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        hint = args.get("hint", "")
        if hint is None:
            hint = ""
        if not isinstance(hint, str) or len(hint) > 80:
            return Decision(False, "voice hint must be short text")
        return Decision(True, "ok")

    def _check_set_tutor_name(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        name = args.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 32:
            return Decision(False, "tutor name must be a short first name")
        return Decision(True, "ok")

    def _check_video_control(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        action = args.get("action")
        if action not in _CONTROLS:
            return Decision(False, "unsupported video action")
        if ctx.playing_video is None:
            return Decision(False, "no video is playing")
        if action == "seek" and not isinstance(args.get("at_s"), (int, float)):
            return Decision(False, "seek needs at_s")
        return Decision(True, "ok")

    def _check_list_apps(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        return Decision(True, "ok")

    def _check_launch_app(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        app_id = args.get("app_id")
        if not isinstance(app_id, str) or app_id not in ctx.enabled_apps:
            return Decision(False, "app is not allowlisted")
        activity = args.get("activity")
        if activity is None:
            return Decision(True, "ok")
        if not isinstance(activity, str):
            return Decision(False, "activity must be a string")
        known = ctx.app_activities.get(app_id, set())
        if activity not in known:
            return Decision(False, "activity is not in the app manifest")
        return Decision(True, "ok")

    def _check_get_skill_status(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        return Decision(True, "ok")

    def _check_record_observation(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        skill_id = args.get("skill_id")
        outcome = args.get("outcome")
        if not isinstance(skill_id, str) or skill_id not in ctx.skills:
            return Decision(False, "skill is not in the skills map")
        if outcome not in _OUTCOMES:
            return Decision(False, "outcome must be correct, with_help, or not_yet")
        evidence = args.get("evidence", "")
        if not isinstance(evidence, str) or len(evidence) > 400:
            return Decision(False, "evidence is too long")
        return Decision(True, "ok")

    def _check_note_interest(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        topic = args.get("topic")
        strength = args.get("strength")
        if not isinstance(topic, str) or not topic.strip() or len(topic) > 60:
            return Decision(False, "topic must be short text")
        if not isinstance(strength, (int, float)) or not 0 <= float(strength) <= 1:
            return Decision(False, "strength must be between 0 and 1")
        return Decision(True, "ok")

    def _check_note_for_next_time(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 280:
            return Decision(False, "note must be 280 characters or fewer")
        return Decision(True, "ok")

    def _check_request_content(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        kind = args.get("kind")
        description = args.get("description")
        if kind not in _KINDS:
            return Decision(False, "content kind must be app, media, or image")
        if not isinstance(description, str) or not description.strip() or len(description) > 300:
            return Decision(False, "description is too long")
        return Decision(True, "ok")

    def _check_flag_for_parent(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        if args.get("severity") not in _SEVERITIES:
            return Decision(False, "severity must be low, medium, or high")
        reason = args.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return Decision(False, "reason is required")
        return Decision(True, "ok")

    def _check_suggest_break(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        return Decision(True, "ok")

    def _check_end_session(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        summary = args.get("summary", "")
        if not isinstance(summary, str) or len(summary) > 600:
            return Decision(False, "summary is too long")
        return Decision(True, "ok")

    def _check_get_observations(self, args: dict[str, object], ctx: PolicyContext) -> Decision:
        return Decision(True, "ok")
