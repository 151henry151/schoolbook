# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
import json
from pathlib import Path

from sqlalchemy import select

from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.models import ApiUsage
from schoolbookd.db.store import Store
from schoolbookd.providers.openai_realtime import RealtimeTalk
from schoolbookd.usage import usage_counters


def test_usage_records_are_numeric_only_deduplicated_and_scoped(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "usage.db")
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id="hannah", first_name="Hannah", birth_year=2022)
    payload = {"total_tokens": 120, "input_tokens": 100, "output_tokens": 20,
               "input_token_details": {"text_tokens": 90, "audio_tokens": 10, "cached_tokens": 80,
                                       "cached_tokens_details": {"text_tokens": 80}},
               "transcript": "private words", "api_key": "secret"}
    for _ in range(2):
        store.record_api_usage("hannah", "realtime", "resp1", "gpt-realtime-2.1", payload)
    with store.session() as db:
        rows = list(db.scalars(select(ApiUsage)))
        assert len(rows) == 1 and rows[0].learner_id == "hannah"
        details = json.loads(rows[0].usage_json)["input_token_details"]
        assert details["cached_tokens_details"] == {"text_tokens": 80}
        assert "private" not in rows[0].usage_json and "secret" not in rows[0].usage_json
    store.delete_learner_data("hannah")
    with store.session() as db:
        assert list(db.scalars(select(ApiUsage))) == []
    assert usage_counters({"input_tokens": -1, "output_tokens": float("nan"), "audio_tokens": True}) == {}


def test_realtime_records_both_kinds_of_usage_even_for_cancelled_responses() -> None:
    records = []
    talk = RealtimeTalk("unused", "help", lambda n, a: {}, on_usage=lambda *args: records.append(args))
    talk.record_usage({"type": "response.done", "response": {"id": "resp1", "status": "cancelled",
                                                           "usage": {"output_tokens": 2}}})
    talk.record_usage({"type": "conversation.item.input_audio_transcription.completed", "item_id": "item1",
                       "transcript": "not copied", "usage": {"input_tokens": 4}})
    assert records == [("realtime", "resp1", "gpt-realtime-2.1", {"output_tokens": 2}),
                       ("transcription", "item1", "gpt-4o-mini-transcribe", {"input_tokens": 4})]
    talk.on_usage = lambda *args: (_ for _ in ()).throw(RuntimeError("disk failure"))
    talk.record_usage({"type": "response.done", "response": {"id": "resp2", "usage": {"output_tokens": 3}}})
