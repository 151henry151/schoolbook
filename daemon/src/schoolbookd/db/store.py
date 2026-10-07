# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Read and write the learner database."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from schoolbookd.db.models import (
    AuditLog,
    ContentRequest,
    Flag,
    ImageRow,
    Interest,
    Learner,
    Note,
    Observation,
    SessionRow,
    Setting,
    Skill,
    SkillState,
    ToolCall,
    Turn,
    Video,
)
from schoolbookd.learner.memory import ProfileInput, mention_interest, next_stretch
from schoolbookd.learner.rules import SkillSnapshot, apply_outcome


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def session(self) -> Session:
        return self._factory()

    def audit(self, db: Session, actor: str, action: str, detail: dict[str, object]) -> None:
        db.add(AuditLog(id=_id(), actor=actor, action=action, detail_json=json.dumps(detail)))

    def upsert_learner(
        self,
        *,
        learner_id: str,
        first_name: str,
        birth_year: int,
        age_profile: str = "age-6",
        avatar: str = "star",
        voice: str = "piper-warm",
        talk_mode: str = "tap",
    ) -> None:
        with self.session() as db:
            row = db.get(Learner, learner_id)
            if row is None:
                db.add(
                    Learner(
                        id=learner_id,
                        first_name=first_name,
                        birth_year=birth_year,
                        age_profile=age_profile,
                        avatar=avatar,
                        voice=voice,
                        talk_mode=talk_mode,
                    )
                )
            else:
                row.first_name = first_name
                row.birth_year = birth_year
                row.age_profile = age_profile
                row.avatar = avatar
                row.voice = voice
                row.talk_mode = talk_mode
            self.audit(db, "parent", "learner.update", {"id": learner_id})
            db.commit()

    def learner(self, learner_id: str) -> Learner | None:
        with self.session() as db:
            return db.get(Learner, learner_id)

    def replace_skills(self, skills: list[Skill]) -> None:
        with self.session() as db:
            for skill in skills:
                existing = db.get(Skill, skill.id)
                if existing is None:
                    db.add(skill)
                else:
                    existing.title = skill.title
                    existing.parent_id = skill.parent_id
                    existing.kid_description = skill.kid_description
                    existing.age_min = skill.age_min
                    existing.age_max = skill.age_max
                    existing.source = skill.source
            db.commit()

    def skill_ids(self) -> set[str]:
        with self.session() as db:
            return set(db.scalars(select(Skill.id)))

    def start_session(self, learner_id: str, model: str) -> str:
        session_id = _id()
        with self.session() as db:
            db.add(SessionRow(id=session_id, learner_id=learner_id, model=model))
            db.commit()
        return session_id

    def open_session(self, learner_id: str) -> SessionRow | None:
        with self.session() as db:
            stmt = (
                select(SessionRow)
                .where(SessionRow.learner_id == learner_id, SessionRow.ended_at.is_(None))
                .order_by(SessionRow.started_at.desc())
            )
            return db.scalars(stmt).first()

    def set_paused(self, session_id: str, paused: bool) -> None:
        with self.session() as db:
            row = db.get(SessionRow, session_id)
            if row is not None and row.ended_at is None:
                row.paused = 1 if paused else 0
                db.commit()

    def add_turn(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        stt_confidence: float | None = None,
    ) -> str:
        turn_id = _id()
        with self.session() as db:
            seq = len(list(db.scalars(select(Turn.id).where(Turn.session_id == session_id))))
            db.add(
                Turn(
                    id=turn_id,
                    session_id=session_id,
                    seq=seq,
                    role=role,
                    text=text,
                    stt_confidence=stt_confidence,
                )
            )
            db.commit()
        return turn_id

    def add_tool_call(
        self,
        turn_id: str,
        tool: str,
        arguments: dict[str, object],
        result: dict[str, object],
        *,
        allowed: bool,
    ) -> None:
        with self.session() as db:
            db.add(
                ToolCall(
                    id=_id(),
                    turn_id=turn_id,
                    tool=tool,
                    input_json=json.dumps(arguments),
                    result_json=json.dumps(result),
                    allowed=1 if allowed else 0,
                )
            )
            db.commit()

    def add_flag(
        self,
        *,
        session_id: str | None,
        turn_id: str | None,
        severity: str,
        reason: str,
        source: str,
        excerpt: str = "",
    ) -> str:
        flag_id = _id()
        with self.session() as db:
            db.add(
                Flag(
                    id=flag_id,
                    session_id=session_id,
                    turn_id=turn_id,
                    severity=severity,
                    reason=reason,
                    source=source,
                    excerpt=excerpt,
                )
            )
            db.commit()
        return flag_id

    def record_observation(
        self,
        *,
        learner_id: str,
        skill_id: str,
        session_id: str | None,
        outcome: str,
        evidence: str,
        observed: bool = False,
    ) -> SkillSnapshot:
        when = _now()
        with self.session() as db:
            state = db.get(SkillState, (learner_id, skill_id))
            prior_days = {
                row.created_at.date()
                for row in db.scalars(
                    select(Observation).where(
                        Observation.learner_id == learner_id,
                        Observation.skill_id == skill_id,
                    )
                )
            }
            prior_days.add(when.date())
            current = SkillSnapshot()
            if state is not None:
                current = SkillSnapshot(
                    state=state.state,
                    mastery=state.mastery,
                    evidence_count=state.evidence_count,
                    distinct_days=len(prior_days),
                    review_stage=state.review_stage,
                )
            updated, review_at = apply_outcome(
                current,
                outcome,
                when=when,
                distinct_days_after=len(prior_days),
                observed=observed,
            )
            if state is None:
                state = SkillState(learner_id=learner_id, skill_id=skill_id)
                db.add(state)
            state.state = updated.state
            state.mastery = updated.mastery
            state.evidence_count = updated.evidence_count
            state.last_seen_at = when
            state.next_review_at = review_at
            state.review_stage = updated.review_stage
            db.add(
                Observation(
                    id=_id(),
                    learner_id=learner_id,
                    skill_id=skill_id,
                    session_id=session_id,
                    outcome=outcome,
                    evidence=("observed: " if observed else "") + evidence,
                    created_at=when,
                )
            )
            db.commit()
            return updated

    def note_interest(self, learner_id: str, topic: str, strength: float) -> None:
        when = _now()
        with self.session() as db:
            row = db.get(Interest, (learner_id, topic))
            if row is None:
                db.add(
                    Interest(
                        learner_id=learner_id,
                        topic=topic,
                        strength=min(1.0, strength),
                        last_mentioned_at=when,
                    )
                )
            else:
                row.strength = mention_interest(row.strength, row.last_mentioned_at, when)
                row.last_mentioned_at = when
            db.commit()

    def add_note(self, learner_id: str, kind: str, text: str, session_id: str | None) -> str:
        note_id = _id()
        with self.session() as db:
            db.add(
                Note(
                    id=note_id,
                    learner_id=learner_id,
                    kind=kind,
                    text=text,
                    source_session_id=session_id,
                )
            )
            db.commit()
        return note_id

    def request_content(self, learner_id: str, kind: str, description: str) -> str:
        request_id = _id()
        with self.session() as db:
            db.add(
                ContentRequest(
                    id=request_id,
                    learner_id=learner_id,
                    kind=kind,
                    description=description,
                )
            )
            db.commit()
        return request_id

    def save_image(self, image_id: str, path: Path, title: str, license_name: str, tags: str) -> None:
        with self.session() as db:
            db.merge(
                ImageRow(
                    id=image_id,
                    path=str(path),
                    title=title,
                    license=license_name,
                    tags=tags,
                )
            )
            db.commit()

    def image_ids(self) -> set[str]:
        with self.session() as db:
            return set(db.scalars(select(ImageRow.id)))

    def end_session(self, session_id: str, reason: str, summary: str, tutor_notes: str) -> None:
        with self.session() as db:
            row = db.get(SessionRow, session_id)
            if row is None or row.ended_at is not None:
                return
            row.ended_at = _now()
            row.end_reason = reason
            row.parent_summary = summary
            row.tutor_notes = tutor_notes
            started = row.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            row.minutes_used = max((row.ended_at - started).total_seconds() / 60, 0)
            if tutor_notes:
                db.add(
                    Note(
                        id=_id(),
                        learner_id=row.learner_id,
                        kind="tutor",
                        text=tutor_notes,
                        source_session_id=session_id,
                    )
                )
            db.commit()

    def profile_input(self, learner_id: str) -> ProfileInput:
        with self.session() as db:
            learner = db.get(Learner, learner_id)
            if learner is None:
                raise KeyError(learner_id)
            notes = list(
                db.scalars(select(Note).where(Note.learner_id == learner_id).order_by(Note.created_at))
            )
            interests = list(db.scalars(select(Interest).where(Interest.learner_id == learner_id)))
            states = list(db.scalars(select(SkillState).where(SkillState.learner_id == learner_id)))
            sessions = list(
                db.scalars(
                    select(SessionRow)
                    .where(SessionRow.learner_id == learner_id, SessionRow.tutor_notes != "")
                    .order_by(SessionRow.started_at.desc())
                )
            )
            now = _now()
            age = max(now.year - learner.birth_year, 0)
            ranked = sorted(interests, key=lambda row: row.strength, reverse=True)
            return ProfileInput(
                name=learner.first_name,
                age=age,
                house_notes=[note.text for note in notes if note.kind == "house"],
                interests=[(row.topic, row.strength) for row in ranked],
                practicing=[row.skill_id for row in states if row.state == "practicing"],
                review_due=[
                    row.skill_id
                    for row in states
                    if row.next_review_at is not None and row.next_review_at <= now
                ],
                tutor_notes=[row.tutor_notes for row in sessions[:3]],
                stretch=self._stretch(db, learner_id),
            )

    def stretch_level(self, learner_id: str, subject: str) -> int:
        with self.session() as db:
            return self._stretch(db, learner_id).get(subject, 3)

    def set_stretch(self, learner_id: str, subject: str, outcome: str) -> int:
        with self.session() as db:
            current = self._stretch(db, learner_id).get(subject, 3)
            updated = next_stretch(current, outcome)
            levels = self._stretch(db, learner_id)
            levels[subject] = updated
            self._put_setting(db, f"stretch:{learner_id}", levels)
            db.commit()
            return updated

    def _stretch(self, db: Session, learner_id: str) -> dict[str, int]:
        raw = self._get_setting(db, f"stretch:{learner_id}")
        if not isinstance(raw, dict):
            return {}
        return {str(key): int(value) for key, value in raw.items()}

    def _get_setting(self, db: Session, key: str) -> object:
        row = db.get(Setting, key)
        if row is None:
            return None
        return json.loads(row.value_json)

    def _put_setting(self, db: Session, key: str, value: object) -> None:
        row = db.get(Setting, key)
        encoded = json.dumps(value)
        if row is None:
            db.add(Setting(key=key, value_json=encoded))
        else:
            row.value_json = encoded

    def get_setting(self, key: str, default: object = None) -> object:
        with self.session() as db:
            value = self._get_setting(db, key)
            return default if value is None else value

    def put_setting(self, key: str, value: object, *, actor: str = "parent") -> None:
        with self.session() as db:
            self._put_setting(db, key, value)
            self.audit(db, actor, "setting.update", {"key": key})
            db.commit()

    def save_video(self, video: Video) -> None:
        with self.session() as db:
            db.merge(video)
            db.commit()

    def video(self, video_id: str) -> Video | None:
        with self.session() as db:
            return db.get(Video, video_id)

    def approved_ids(self) -> set[str]:
        with self.session() as db:
            stmt = select(Video.id).where(Video.verdict == "approved")
            return set(db.scalars(stmt))

    def blocked_ids(self) -> set[str]:
        with self.session() as db:
            stmt = select(Video.id).where(Video.verdict == "blocked")
            return set(db.scalars(stmt))

    def rejected_ids(self) -> set[str]:
        with self.session() as db:
            stmt = select(Video.id).where(Video.verdict.in_(("rejected", "blocked")))
            return set(db.scalars(stmt))

    def block_video(self, video_id: str) -> None:
        with self.session() as db:
            row = db.get(Video, video_id)
            if row is None:
                row = Video(id=video_id, source="youtube", source_ref=video_id, verdict="blocked")
                db.add(row)
            row.verdict = "blocked"
            self.audit(db, "parent", "video.block", {"id": video_id})
            db.commit()

    def block_channel(self, channel_id: str) -> None:
        with self.session() as db:
            blocked = self._get_setting(db, "blocked_channels")
            ids = set(blocked) if isinstance(blocked, list) else set()
            ids.add(channel_id)
            self._put_setting(db, "blocked_channels", sorted(ids))
            for video in db.scalars(select(Video).where(Video.channel_id == channel_id)):
                video.verdict = "blocked"
            self.audit(db, "parent", "channel.block", {"id": channel_id})
            db.commit()

    def blocked_channels(self) -> set[str]:
        value = self.get_setting("blocked_channels", [])
        if isinstance(value, list):
            return {str(item) for item in value}
        return set()

    def forget(self, kind: str, learner_id: str, target: str) -> None:
        with self.session() as db:
            if kind == "note":
                row = db.get(Note, target)
                if row is not None and row.learner_id == learner_id:
                    db.delete(row)
            elif kind == "interest":
                interest = db.get(Interest, (learner_id, target))
                if interest is not None:
                    db.delete(interest)
            elif kind == "observation":
                observation = db.get(Observation, target)
                if observation is not None and observation.learner_id == learner_id:
                    skill_id = observation.skill_id
                    db.delete(observation)
                    db.flush()
                    self._recompute_skill(db, learner_id, skill_id)
            elif kind == "session":
                session_row = db.get(SessionRow, target)
                if session_row is not None and session_row.learner_id == learner_id:
                    for turn in db.scalars(select(Turn).where(Turn.session_id == target)):
                        for call in db.scalars(select(ToolCall).where(ToolCall.turn_id == turn.id)):
                            db.delete(call)
                        db.delete(turn)
                    for obs in db.scalars(select(Observation).where(Observation.session_id == target)):
                        db.delete(obs)
                    for note in db.scalars(select(Note).where(Note.source_session_id == target)):
                        db.delete(note)
                    db.delete(session_row)
            self.audit(db, "parent", "forget", {"kind": kind, "target": target})
            db.commit()

    def _recompute_skill(self, db: Session, learner_id: str, skill_id: str) -> None:
        rows = list(
            db.scalars(
                select(Observation)
                .where(Observation.learner_id == learner_id, Observation.skill_id == skill_id)
                .order_by(Observation.created_at)
            )
        )
        state = db.get(SkillState, (learner_id, skill_id))
        if not rows:
            if state is not None:
                db.delete(state)
            return
        current = SkillSnapshot()
        review_at = None
        days: set[object] = set()
        for row in rows:
            days.add(row.created_at.date())
            current, review_at = apply_outcome(
                current,
                row.outcome,
                when=row.created_at,
                distinct_days_after=len(days),
                observed=row.evidence.startswith("observed:"),
            )
        if state is None:
            state = SkillState(learner_id=learner_id, skill_id=skill_id)
            db.add(state)
        state.state = current.state
        state.mastery = current.mastery
        state.evidence_count = current.evidence_count
        state.review_stage = current.review_stage
        state.next_review_at = review_at
        state.last_seen_at = rows[-1].created_at

    def export_markdown(self, learner_id: str) -> str:
        data = self.profile_input(learner_id)
        return "\n".join(
            [
                f"# {data.name}",
                "",
                data.house_notes and "\n".join(f"- {note}" for note in data.house_notes) or "",
                "",
                "## Interests",
                "\n".join(f"- {topic}" for topic, _ in data.interests) or "- none",
            ]
        )

    def delete_learner_data(self, learner_id: str) -> None:
        with self.session() as db:
            sessions = list(db.scalars(select(SessionRow).where(SessionRow.learner_id == learner_id)))
            for session_row in sessions:
                turns = list(db.scalars(select(Turn).where(Turn.session_id == session_row.id)))
                for turn in turns:
                    for call in db.scalars(select(ToolCall).where(ToolCall.turn_id == turn.id)):
                        db.delete(call)
                    db.delete(turn)
                db.delete(session_row)
            for model in (Observation, Interest, Note, SkillState, ContentRequest):
                column = model.learner_id
                for row in db.scalars(select(model).where(column == learner_id)):
                    db.delete(row)
            learner = db.get(Learner, learner_id)
            if learner is not None:
                db.delete(learner)
            self.audit(db, "parent", "learner.delete", {"id": learner_id})
            db.commit()
