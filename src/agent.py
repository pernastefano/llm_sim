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

from .tools import CalculatorTool, FakeSearchTool, ToolResult
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
        self.search = FakeSearchTool()

    # -- heuristics ----------------------------------------------------------

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

        steps.append(f"Received user query: '{query}'")

        # ── Step 1: Check for arithmetic ────────────────────────────────────
        steps.append("Step 1 — Intent detection: scanning for arithmetic expression.")
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

            # ── Step 2: Check for factual question ──────────────────────────
            steps.append("Step 2 — Intent detection: scanning for factual question.")
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
        )
