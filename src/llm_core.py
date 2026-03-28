"""
llm_core.py — Simulates next-token generation with softmax + temperature sampling.

The "model" has no learned weights.  Instead:
  1. Pseudo-random base scores are assigned to each candidate token.
  2. A repetition penalty discourages recently-seen tokens.
  3. The target token is boosted so the demo produces coherent output
     while the other candidates still form a realistic probability table.
  4. softmax + temperature converts scores to a probability distribution.
  5. Each generation step is fully logged to the trace.

Clarity and observability are the primary design goals here, not performance.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .tokenizer import SimpleTokenizer
from .trace import Trace


@dataclass
class GenerationConfig:
    temperature: float = 0.7   # Higher → flatter distribution, more "randomness"
    top_k: int = 6             # Candidates shown per step in the trace
    seed: int = 42             # Fixed seed for reproducible demos


class LLMCore:
    """
    Token-by-token generation engine.

    Public surface:
        generate(prompt, target_tokens, trace) -> str
    """

    def __init__(
        self,
        tokenizer: SimpleTokenizer,
        config: GenerationConfig | None = None,
    ) -> None:
        self.tokenizer = tokenizer
        self.cfg = config or GenerationConfig()
        # Fixed seed so re-running main.py always produces the same trace.
        self._rng = random.Random(self.cfg.seed)

    # -- internals -----------------------------------------------------------

    def _base_scores(
        self, candidates: list[str], recent_tokens: set[str]
    ) -> list[float]:
        """
        Assign pseudo-random scores.

        Repetition penalty: tokens that already appeared in the recent
        context window get a 75 % score reduction, encouraging diversity.
        """
        scores: list[float] = []
        for token in candidates:
            s = self._rng.uniform(0.2, 3.0)
            if token in recent_tokens:
                s *= 0.25
            scores.append(s)
        return scores

    @staticmethod
    def _softmax(scores: list[float], temperature: float) -> list[float]:
        """
        Temperature-scaled softmax.

        Subtracting the max before exp is the standard numerical-stability trick
        (prevents overflow without changing the output distribution).
        """
        scaled = [s / max(temperature, 1e-8) for s in scores]
        max_s = max(scaled)
        exps = [math.exp(s - max_s) for s in scaled]
        total = sum(exps)
        return [e / total for e in exps]

    # -- public API ----------------------------------------------------------

    def generate(
        self,
        prompt: str,
        target_tokens: list[str],
        trace: Trace,
    ) -> str:
        """
        Simulate generation of `target_tokens` one at a time.

        Why pre-specified targets?
        --------------------------
        Without learned weights there is no way to infer which token is
        semantically correct.  Pre-specifying the target keeps the output
        coherent (so the demo makes sense) while still exercising the full
        probability-sampling machinery for educational purposes.

        At each step:
          - `top_k` candidates are drawn (target + random words from vocab).
          - The target token receives a score boost so it usually wins.
          - The full probability table is logged for inspection.
        """
        context_ids = self.tokenizer.encode(prompt)
        generated: list[str] = []

        for step_i, target in enumerate(target_tokens):
            # Build candidate pool: the correct target + random distractor tokens.
            vocab_keys = [
                t
                for t in self.tokenizer.vocab
                if t != target and not t.startswith("[")
            ]
            n_others = min(self.cfg.top_k - 1, len(vocab_keys))
            others = self._rng.sample(vocab_keys, n_others)
            candidates = [target] + others
            self._rng.shuffle(candidates)

            # Score: random base + repetition penalty from last 10 context tokens.
            recent = set(self.tokenizer.decode(context_ids[-10:]).split())
            scores = self._base_scores(candidates, recent)

            # Boost target so it tends to win — keeps the demo coherent.
            # The boost is visible in the probability table, which is the point.
            target_idx = candidates.index(target)
            scores[target_idx] *= 2.8

            probs = self._softmax(scores, self.cfg.temperature)

            # We force the target here; a real sampler would draw from `probs`.
            selected_token = target
            selected_id = self.tokenizer.vocab[target]

            # Sorted candidate table for the trace (highest probability first).
            candidate_table = sorted(
                [
                    {
                        "token": c,
                        "score": round(s, 4),
                        "probability": round(p, 4),
                    }
                    for c, s, p in zip(candidates, scores, probs)
                ],
                key=lambda x: -x["probability"],  # type: ignore[index]
            )

            generated.append(selected_token)
            context_ids.append(selected_id)
            partial = " ".join(generated)
            selected_prob = next(
                c["probability"] for c in candidate_table if c["token"] == selected_token
            )

            trace.add(
                name=f"generation_step_{step_i}",
                description=f"Step {step_i}: sampled token '{selected_token}' "
                f"(p={selected_prob:.4f})",
                data={
                    "step": step_i,
                    "context_length": len(context_ids),
                    "context_preview": self.tokenizer.decode(context_ids[-10:]),
                    "candidates": candidate_table,
                    "selected_token": selected_token,
                    "selected_probability": selected_prob,
                    "partial_output": partial,
                },
            )

        return " ".join(generated)
