# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Tool-use loop. The model never touches the OS, network, or database."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from schoolbookd.policy.output_check import OutputCheck, looks_like_distress
from schoolbookd.policy.tools import PolicyContext, ToolPolicy
from schoolbookd.providers.base import LLMProvider, LLMRequest, SystemBlock
from schoolbookd.tutor.speech import chunk_sentences

FALLBACK = "Let's try one small thing. What do you want to look at?"
Execute = Callable[[str, dict[str, object]], dict[str, object]]


@dataclass
class ToolRecord:
    name: str
    arguments: dict[str, object]
    allowed: bool
    result: dict[str, object]


@dataclass
class TurnOutcome:
    sentences: list[str]
    tool_calls: list[ToolRecord]
    flagged: bool
    flag_reason: str
    ended: bool
    redirected: bool


@dataclass
class TutorLoop:
    llm: LLMProvider
    policy: ToolPolicy
    execute: Execute
    output_check: OutputCheck
    model: str
    max_tool_calls: int = 6
    wall_clock_s: float = 20
    max_sentences: int = 3
    max_words: int = 12
    clock: Callable[[], float] = field(default=lambda: 0.0)
    history_limit: int = 12

    def run_turn(
        self,
        child_text: str,
        *,
        system: list[SystemBlock],
        history: list[dict[str, object]],
        policy_context: PolicyContext,
    ) -> TurnOutcome:
        if not child_text.strip():
            return TurnOutcome(["I didn't catch that."], [], False, "", False, False)
        started = self.clock()
        messages = _fold(history, self.history_limit)
        messages.append({"role": "user", "content": child_text})
        records: list[ToolRecord] = []
        spoken = ""
        flagged = looks_like_distress(child_text)
        flag_reason = "distress in the child's words" if flagged else ""
        ended = False
        rounds = 0
        while rounds < self.max_tool_calls + 1:
            rounds += 1
            if self.clock() - started > self.wall_clock_s:
                break
            response = self.llm.complete(
                LLMRequest(model=self.model, system=system, messages=messages)
            )
            if response.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.text,
                        "tool_calls": [call.name for call in response.tool_calls],
                    }
                )
            for call in response.tool_calls:
                policy_context.tool_calls_used = len(records)
                decision = self.policy.check(call.name, call.arguments, policy_context)
                if decision.allowed:
                    result = self.execute(call.name, call.arguments)
                else:
                    result = {"error": decision.reason}
                if call.name == "flag_for_parent" and decision.allowed:
                    flagged = True
                    flag_reason = str(call.arguments.get("reason", flag_reason))
                if call.name == "end_session" and decision.allowed:
                    ended = True
                records.append(ToolRecord(call.name, call.arguments, decision.allowed, result))
                messages.append({"role": "tool", "name": call.name, "content": json.dumps(result)})
            if response.text.strip():
                spoken = response.text
                break
            if not response.tool_calls:
                break
        if not spoken:
            spoken = FALLBACK
        sentences, redirected = self._speak(spoken)
        return TurnOutcome(sentences, records, flagged, flag_reason, ended, redirected)

    def _speak(self, text: str) -> tuple[list[str], bool]:
        sentences = chunk_sentences(
            text, max_sentences=self.max_sentences, max_words=self.max_words
        )
        redirected = False
        checked: list[str] = []
        for sentence in sentences:
            hit = self.output_check.inspect(sentence)
            if hit is None:
                checked.append(sentence)
                continue
            redirected = True
            checked = [hit.replacement]
            break
        return checked or [FALLBACK], redirected


def _fold(history: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    if len(history) <= limit:
        return list(history)
    older = history[:-limit]
    snippets: list[str] = []
    for message in older:
        content = message.get("content")
        if isinstance(content, str) and content:
            snippets.append(content)
    summary = "Earlier: " + " ".join(snippets)
    return [{"role": "system", "content": summary[:800]}, *history[-limit:]]
