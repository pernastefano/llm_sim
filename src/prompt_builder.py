"""
prompt_builder.py — Composes a structured prompt from system + user text.

Intentionally minimal: this component has exactly one responsibility.
It never touches the tokenizer, the trace, or any other subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptComponents:
    """Immutable snapshot of a fully-built prompt."""

    system_prompt: str
    user_input: str
    full_prompt: str


class PromptBuilder:
    """
    Combines a fixed system prompt with a per-request user message.

    The template uses labelled sections so both humans and the tokenizer
    can easily identify where each part begins.
    """

    _TEMPLATE = "[SYSTEM]\n{system}\n\n[USER]\n{user}\n\n[ASSISTANT]\n"

    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt

    def build(self, user_input: str) -> PromptComponents:
        full = self._TEMPLATE.format(system=self.system_prompt, user=user_input)
        return PromptComponents(
            system_prompt=self.system_prompt,
            user_input=user_input,
            full_prompt=full,
        )
