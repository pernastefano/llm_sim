"""
tokenizer.py — Simple whitespace + punctuation tokenizer with a dynamic vocabulary.

Design goals:
- No external dependencies.
- Every new surface form encountered at encode() time gets a unique integer id.
- encode() and decode() are exact inverses (up to whitespace collapsing).
- The vocabulary is intentionally dynamic so running on any text "just works".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Matches either a run of word characters (\w+) or any single
# non-word, non-space character (punctuation, symbols, etc.)
_TOKEN_RE = re.compile(r"\w+|[^\w\s]")


@dataclass
class SimpleTokenizer:
    """
    Toy tokenizer used to make the generation loop concrete and observable.

    Special tokens occupy ids 0–3 so real word ids start at 4.
    """

    _vocab: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _rev: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    _next_id: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        for special in ("[PAD]", "[UNK]", "[BOS]", "[EOS]"):
            self._register(special)

    # -- internals -----------------------------------------------------------

    def _register(self, token: str) -> int:
        """Add token to vocab if unknown; always return its id."""
        if token not in self._vocab:
            tid = self._next_id
            self._vocab[token] = tid
            self._rev[tid] = token
            self._next_id += 1
        return self._vocab[token]

    # -- public API ----------------------------------------------------------

    def tokenize(self, text: str) -> list[str]:
        """Split text into surface-form tokens without modifiying the vocab."""
        return _TOKEN_RE.findall(text)

    def encode(self, text: str) -> list[int]:
        """Tokenize and map every token to its integer id, registering unknowns."""
        return [self._register(t) for t in self.tokenize(text)]

    def decode(self, ids: list[int]) -> str:
        """Map integer ids back to space-joined surface forms."""
        return " ".join(self._rev.get(i, "[UNK]") for i in ids)

    @property
    def vocab(self) -> dict[str, int]:
        return dict(self._vocab)

    @property
    def vocab_size(self) -> int:
        return self._next_id
