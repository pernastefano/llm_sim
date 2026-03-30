"""
pipeline.py — Top-level orchestrator that wires all components together.

Call `LLMPipeline().run(query)` to execute the full simulation and receive
a `PipelineResult` containing the final answer and the complete trace.

Pipeline stages (in order):
  1. input        — record raw user query
  2. prompt       — combine system + user text
  3. tokenization — encode the full prompt
  4. reasoning    — agent analyses query, may call tools
  5. generation   — LLM core generates tokens one-by-one
  6. final_answer — combine tool output + generated text
"""
from __future__ import annotations

from dataclasses import dataclass

from .agent import ReasoningAgent, ReasoningResult
from .llm_core import GenerationConfig, LLMCore
from .prompt_builder import PromptBuilder
from .tokenizer import SimpleTokenizer
from .trace import Trace

_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. "
    "You reason step-by-step and use tools when needed. "
    "Always provide clear, concise answers."
)


@dataclass
class PipelineResult:
    query: str
    final_answer: str
    trace: Trace


class LLMPipeline:
    """
    Stateless pipeline factory.

    Each call to `.run()` creates a fresh Trace, executes all stages,
    and returns a self-contained PipelineResult.
    """

    def __init__(self, gen_config: GenerationConfig | None = None) -> None:
        self.prompt_builder = PromptBuilder(_SYSTEM_PROMPT)
        self.tokenizer = SimpleTokenizer()
        self.llm = LLMCore(self.tokenizer, config=gen_config)
        self.agent = ReasoningAgent()

    # -- public API ----------------------------------------------------------

    def run(self, user_query: str) -> PipelineResult:
        trace = Trace()

        # ── 1. Input ────────────────────────────────────────────────────────
        trace.add(
            name="input",
            description="Raw user input received by the pipeline",
            data={"user_query": user_query},
        )

        # ── 2. Prompt construction ───────────────────────────────────────────
        prompt = self.prompt_builder.build(user_query)
        trace.add(
            name="prompt_construction",
            description="System prompt merged with user input into a full prompt",
            data={
                "system_prompt": prompt.system_prompt,
                "user_input": prompt.user_input,
                "full_prompt": prompt.full_prompt,
            },
        )

        # ── 3. Tokenisation ─────────────────────────────────────────────────
        token_ids = self.tokenizer.encode(prompt.full_prompt)
        tokens = self.tokenizer.tokenize(prompt.full_prompt)
        trace.add(
            name="tokenization",
            description="Full prompt tokenized and mapped to integer IDs",
            data={
                "token_count": len(token_ids),
                # Limit preview to first 60 tokens so the trace stays readable.
                "tokens_preview": tokens[:60],
                "token_ids_preview": token_ids[:60],
                "vocabulary_size_after_encoding": self.tokenizer.vocab_size,
            },
        )

        # ── 4. Agent reasoning ──────────────────────────────────────────────
        reasoning = self.agent.reason(user_query, trace)

        # ── 5. Generation ────────────────────────────────────────────────────
        # Build the target answer BEFORE generating so vocabulary is consistent.
        target_answer = self._build_target_answer(reasoning)
        self.tokenizer.encode(target_answer)  # registers target tokens
        target_tokens = self.tokenizer.tokenize(target_answer)

        trace.add(
            name="generation_start",
            description="LLM core is about to generate tokens one-by-one",
            data={
                "llm_prompt_preview": reasoning.llm_prompt[:300],
                "target_token_count": len(target_tokens),
                "temperature": self.llm.cfg.temperature,
                "top_k": self.llm.cfg.top_k,
                "note": (
                    "target_tokens are pre-specified so the demo output is coherent. "
                    "All probability machinery still runs as in a real LLM."
                ),
            },
        )

        generated_text = self.llm.generate(
            prompt=reasoning.llm_prompt,
            target_tokens=target_tokens,
            trace=trace,
        )

        # ── 6. Final answer ──────────────────────────────────────────────────
        final_answer = self._compose_answer(reasoning, generated_text)
        trace.add(
            name="final_answer",
            description="Final answer assembled from tool output and generated text",
            data={
                "tool_name": reasoning.tool_used,
                "tool_output": (
                    reasoning.tool_result.output
                    if reasoning.tool_result and reasoning.tool_result.success
                    else None
                ),
                "generated_text": generated_text,
                "final_answer": final_answer,
            },
        )

        return PipelineResult(query=user_query, final_answer=final_answer, trace=trace)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _build_target_answer(reasoning: ReasoningResult) -> str:
        """
        Produce a short, plausible answer string to drive the generation loop.

        Without learned weights there is no way to infer what the model
        "would" say.  Pre-specifying the target keeps the output coherent
        while the generation loop still exercises softmax, temperature, and
        probability tables — which is the educational point.
        """
        if reasoning.tool_result and reasoning.tool_result.success:
            if reasoning.tool_used == "calculator":
                return f"The result is {reasoning.tool_result.output} ."
            if reasoning.tool_used == "clock":
                return reasoning.tool_result.output
            if reasoning.tool_used == "search":
                # Use first 30 words from the search result to keep it concise.
                words = reasoning.tool_result.output.split()[:30]
                return " ".join(words) + " ."
        if reasoning.intent == "greeting":
            return "Hello ! How can I assist you today ?"
        if reasoning.intent == "identity":
            return "I am a simulated AI assistant . I can answer questions and perform calculations ."
        if reasoning.intent == "wellbeing":
            return "I am functioning well , thank you for asking !"
        return "I am sorry , I cannot help with that request ."

    @staticmethod
    def _compose_answer(reasoning: ReasoningResult, generated_text: str) -> str:
        """Combine tool output (if any) with the generated text."""
        parts: list[str] = []
        if reasoning.tool_result and reasoning.tool_result.success:
            parts.append(f"[Tool: {reasoning.tool_used}]\n{reasoning.tool_result.output}\n")
        parts.append(f"[Generated response]\n{generated_text}")
        return "\n".join(parts)
