# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""SQLite tables from the design spec."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now().astimezone()


class Learner(Base):
    __tablename__ = "learners"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    first_name: Mapped[str] = mapped_column(String)
    birth_year: Mapped[int] = mapped_column(Integer)
    age_profile: Mapped[str] = mapped_column(String)
    avatar: Mapped[str] = mapped_column(String, default="star")
    voice: Mapped[str] = mapped_column(String, default="piper-warm")
    talk_mode: Mapped[str] = mapped_column(String, default="handsfree")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str] = mapped_column(String, default="")
    minutes_used: Mapped[float] = mapped_column(Float, default=0)
    model: Mapped[str] = mapped_column(String, default="")
    parent_summary: Mapped[str] = mapped_column(Text, default="")
    tutor_notes: Mapped[str] = mapped_column(Text, default="")
    paused: Mapped[int] = mapped_column(Integer, default=0)


class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text, default="")
    stt_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ToolCall(Base):
    __tablename__ = "tool_calls"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey("turns.id"))
    tool: Mapped[str] = mapped_column(String)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    allowed: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String)
    kid_description: Mapped[str] = mapped_column(Text, default="")
    age_min: Mapped[int] = mapped_column(Integer, default=4)
    age_max: Mapped[int] = mapped_column(Integer, default=8)
    source: Mapped[str] = mapped_column(String, default="core")


class SkillState(Base):
    __tablename__ = "skill_states"
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String, default="not_seen")
    mastery: Mapped[float] = mapped_column(Float, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_stage: Mapped[int] = mapped_column(Integer, default=0)


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    outcome: Mapped[str] = mapped_column(String)
    evidence: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Interest(Base):
    __tablename__ = "interests"
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), primary_key=True)
    topic: Mapped[str] = mapped_column(String, primary_key=True)
    strength: Mapped[float] = mapped_column(Float, default=0)
    last_mentioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"))
    kind: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    source_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, default="youtube")
    source_ref: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    channel_id: Mapped[str] = mapped_column(String, default="")
    channel_title: Mapped[str] = mapped_column(String, default="")
    duration_s: Mapped[int] = mapped_column(Integer, default=0)
    start_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verdict: Mapped[str] = mapped_column(String, default="")
    verdict_reasons: Mapped[str] = mapped_column(Text, default="")
    est_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vetted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    times_played: Mapped[int] = mapped_column(Integer, default=0)
    made_for_kids: Mapped[int] = mapped_column(Integer, default=0)
    embeddable: Mapped[int] = mapped_column(Integer, default=1)
    age_restricted: Mapped[int] = mapped_column(Integer, default=0)
    live: Mapped[int] = mapped_column(Integer, default=0)
    short: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String, default="en")


class VideoTag(Base):
    __tablename__ = "video_tags"
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    tag: Mapped[str] = mapped_column(String, primary_key=True)


class VideoSkill(Base):
    __tablename__ = "video_skills"
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String, primary_key=True)


class ImageRow(Base):
    __tablename__ = "images"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    path: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    license: Mapped[str] = mapped_column(String)
    tags: Mapped[str] = mapped_column(Text, default="")


class ContentRequest(Base):
    __tablename__ = "content_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"))
    kind: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Flag(Base):
    __tablename__ = "flags"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="null")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ModelExchange(Base):
    """Every model request and response, including tool calls, for the session log."""

    __tablename__ = "model_exchanges"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String)
    turn_id: Mapped[str] = mapped_column(String)
    request_json: Mapped[str] = mapped_column(Text)
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("app_id"),)
    app_id: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    time_cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activities_json: Mapped[str] = mapped_column(Text, default="[]")
