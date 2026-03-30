"""
agent.py — Reasoning layer that analyses queries, calls tools, and composes
the augmented prompt fed to LLMCore.

Design intent:
  - Every decision is logged explicitly so users can follow the reasoning.
  - The agent is kept intentionally simple (rule-based heuristics) because
    the goal is observability, not academic NLU quality.
  - Tool calls are recorded in the trace with full input/output detail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .tools import CalculatorTool, ClockTool, FakeSearchTool, ToolResult
from .trace import Trace


@dataclass
class ReasoningResult:
    """Everything the agent produced and decided during a single request."""

    query: str
    reasoning_steps: list[str]
    tool_used: str | None
    tool_input: str | None
    tool_result: ToolResult | None
    llm_prompt: str
    intent: str | None = None  # e.g. "greeting", "identity", "wellbeing"


class ReasoningAgent:
    """
    Lightweight rule-based reasoning agent.

    Workflow:
      1. Detect whether the query contains arithmetic → use Calculator.
      2. Otherwise detect whether it is a factual question → use Search.
      3. Compose an augmented LLM prompt (with tool context if available).
      4. Record every decision in the trace.
    """

    def __init__(self) -> None:
        self.calculator = CalculatorTool()
        self.clock = ClockTool()
        self.search = FakeSearchTool()

    # -- heuristics ----------------------------------------------------------

    @staticmethod
    def _detect_conversational_intent(query: str) -> str | None:
        """
        Return a conversational intent tag if the query is not a
        knowledge/math request, so it can be answered without tools.

        Recognised intents:
          "greeting"  — hello, hi, hey, …
          "identity"  — what is your name, who are you, …
          "wellbeing" — how are you, are you ok, …
        """
        q = query.lower().strip().rstrip("?.!,")

        _GREETING_TOKENS = {
            "hello", "hi", "hey", "greetings", "howdy",
            "good morning", "good afternoon", "good evening", "good night",
            "ciao", "salut", "hola",
        }
        _IDENTITY_PHRASES = (
            "what is your name",
            "what's your name",
            "who are you",
            "what are you",
            "what can you do",
            "tell me about yourself",
            "introduce yourself",
            "your name",
        )
        _WELLBEING_PHRASES = (
            "how are you",
            "how do you do",
            "how are you doing",
            "are you ok",
            "are you fine",
            "how is it going",
            "how's it going",
        )

        # Time/date queries are handled by the Clock tool, not as conversational.
        _TIME_PHRASES = (
            "what time is it",
            "what's the time",
            "what is the time",
            "current time",
            "what day is it",
            "what is today",
            "what's today",
            "what is the date",
            "what's the date",
            "current date",
            "today's date",
        )
        for phrase in _TIME_PHRASES:
            if phrase in q:
                return None  # let the Clock tool handle it

        # Greeting: query is (or starts with) a greeting token.
        first_token = q.split()[0] if q.split() else ""
        if q in _GREETING_TOKENS or first_token in _GREETING_TOKENS:
            return "greeting"

        for phrase in _IDENTITY_PHRASES:
            if phrase in q:
                return "identity"

        for phrase in _WELLBEING_PHRASES:
            if phrase in q:
                return "wellbeing"

        return None

    @staticmethod
    def _is_time_query(query: str) -> bool:
        """
        Return True if the query is asking for the current time or date.
        """
        _TIME_PHRASES = (
            "what time is it",
            "what's the time",
            "what is the time",
            "current time",
            "what day is it",
            "what is today",
            "what's today",
            "what is the date",
            "what's the date",
            "current date",
            "today's date",
        )
        q = query.lower().strip().rstrip("?.!,")
        return any(phrase in q for phrase in _TIME_PHRASES)

    @staticmethod
    def _extract_math(query: str) -> str | None:
        """
        Return the first arithmetic sub-expression if the query implies
        calculation.  We require either an explicit trigger word OR a
        bare numeric expression with an operator.
        """
        math_triggers = (
            "calculate",
            "compute",
            "what is",
            "how much is",
            "solve",
            "evaluate",
        )
        has_trigger = any(t in query.lower() for t in math_triggers)
        has_bare_expr = bool(re.search(r"\d+\s*[\+\-\*\/]\s*\d+", query))

        if not (has_trigger or has_bare_expr):
            return None

        match = re.search(r"[\d\s\+\-\*\/\(\)\.]+[\d\)]+", query)
        return match.group().strip() if match else None

    @staticmethod
    def _extract_search_topic(query: str) -> str | None:
        """
        Return the topic to look up if the query is a factual question.
        We scan for common question prefixes and extract the subject.
        """
        triggers = (
            "what is",
            "what are",
            "explain",
            "tell me about",
            "define",
            "how does",
            "describe",
        )
        q = query.lower()
        for trigger in triggers:
            if trigger in q:
                topic = q.split(trigger)[-1].strip().rstrip("?.,!").strip()
                return topic if topic else None
        return None

    # -- main entry point ----------------------------------------------------

    def reason(self, query: str, trace: Trace) -> ReasoningResult:
        """
        Analyse `query`, optionally invoke a tool, and return a
        ReasoningResult.  All decisions are appended to `trace`.
        """
        steps: list[str] = []
        tool_used: str | None = None
        tool_input: str | None = None
        tool_result: ToolResult | None = None
        intent: str | None = None

        steps.append(f"Received user query: '{query}'")

        # ── Step 0: Check for conversational intent ──────────────────────────
        steps.append("Step 0 — Intent detection: scanning for conversational intent.")
        intent = self._detect_conversational_intent(query)
        if intent:
            steps.append(f"  → Conversational intent detected: '{intent}'")
            steps.append("  → Decision: no tool needed, compose direct response.")
        else:
            steps.append("  → No conversational intent detected.")

            # ── Step 1: Check for time/date query ─────────────────────────────
            steps.append("Step 1 — Intent detection: checking for time or date query.")
            if self._is_time_query(query):
                steps.append("  → Time/date query detected.")
                steps.append("  → Decision: invoke Clock tool.")
                tool_used = self.clock.name
                tool_input = query
                tool_result = self.clock.run(query)
                steps.append(f"  → Clock returned: {tool_result.output}")
            else:
                steps.append("  → No time/date query detected.")

            # ── Step 2: Check for arithmetic ─────────────────────────────────
            if tool_used is None:
              steps.append("Step 2 — Intent detection: scanning for arithmetic expression.")
              math_expr = self._extract_math(query)

              if math_expr:
                  steps.append(f"  → Arithmetic expression found: '{math_expr}'")
                  steps.append("  → Decision: invoke Calculator tool.")
                  tool_used = self.calculator.name
                  tool_input = math_expr
                  tool_result = self.calculator.run(math_expr)
                  if tool_result.success:
                      steps.append(f"  → Calculator returned: {tool_result.output}")
                  else:
                      steps.append(f"  → Calculator failed: {tool_result.error}")

              else:
                  steps.append("  → No arithmetic detected.")

                  # ── Step 3: Check for factual question ───────────────────────
                  steps.append("Step 3 — Intent detection: scanning for factual question.")
                  topic = self._extract_search_topic(query)

                  if topic:
                      steps.append(f"  → Factual topic identified: '{topic}'")
                      steps.append("  → Decision: invoke Search tool.")
                      tool_used = self.search.name
                      tool_input = topic
                      tool_result = self.search.run(topic)
                      if tool_result.success:
                          steps.append(
                              f"  → Search returned {len(tool_result.output)} chars of context."
                          )
                      else:
                          steps.append(f"  → Search found nothing: {tool_result.error}")
                  else:
                      steps.append("  → Not a recognised factual question.  No tool needed.")

        # ── Step 3: Compose augmented LLM prompt ────────────────────────────
        steps.append("Step 3 — Composing internal LLM prompt.")
        if tool_result and tool_result.success:
            llm_prompt = (
                f"Context retrieved by tools:\n{tool_result.output}\n\n"
                f"Using the context above, answer concisely:\n{query}"
            )
            steps.append("  → Prompt augmented with tool-retrieved context.")
        else:
            llm_prompt = f"Answer the following question concisely:\n{query}"
            steps.append("  → No tool context available; using plain prompt.")

        steps.append("Reasoning complete.  Handing off to LLM core.")

        trace.add(
            name="agent_reasoning",
            description="Agent analysed the query, selected tools, and composed LLM prompt",
            data={
                "query": query,
                "reasoning_steps": steps,
                "tool_used": tool_used,
                "tool_input": tool_input,
                "tool_result": (
                    {
                        "tool_name": tool_result.tool_name,
                        "input": tool_result.input,
                        "output": tool_result.output,
                        "success": tool_result.success,
                        "error": tool_result.error,
                    }
                    if tool_result
                    else None
                ),
                "llm_prompt": llm_prompt,
            },
        )

        return ReasoningResult(
            query=query,
            reasoning_steps=steps,
            tool_used=tool_used,
            tool_input=tool_input,
            tool_result=tool_result,
            llm_prompt=llm_prompt,
            intent=intent,
        )
