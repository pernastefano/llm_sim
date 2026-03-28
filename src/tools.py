"""
tools.py — Self-contained tool implementations used by the reasoning agent.

Design rules:
  - Each tool is a plain class with a `.run(input) -> ToolResult` method.
  - Tools never import from other project modules (no circular deps).
  - CalculatorTool uses a strict input whitelist + AST-based evaluation —
    eval() is intentionally avoided to eliminate any code-injection surface.
  - FakeSearchTool uses a static in-memory knowledge base (no network calls).
"""
from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Uniform return type for all tools."""

    tool_name: str
    input: str
    output: str
    success: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

# Only digits, whitespace, and the standard arithmetic/grouping characters.
# ** (power) is intentionally excluded to keep the surface tiny and safe.
_SAFE_EXPR_RE = re.compile(r"^[\d\s\+\-\*\/\(\)\.]+$")

# Allowed binary and unary operators — no builtins, no attribute access.
_ALLOWED_BIN_OPS: dict[type, object] = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
}
_ALLOWED_UNARY_OPS: dict[type, object] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Guard against astronomically large intermediate results.
_MAX_RESULT_MAGNITUDE = 1e300
_MAX_DEPTH = 50


def _eval_node(node: ast.AST, depth: int = 0) -> float | int:
    """
    Recursively evaluate a safe arithmetic AST node.

    Only numeric literals, and the four basic arithmetic operators (+, -, *, /)
    are permitted.  Any other node type raises ValueError immediately.
    """
    if depth > _MAX_DEPTH:
        raise ValueError("Expression is too deeply nested.")

    if isinstance(node, ast.Expression):
        return _eval_node(node.body, depth)

    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsupported literal type: {type(node.value).__name__}")
        return node.value

    if isinstance(node, ast.BinOp):
        op_fn = _ALLOWED_BIN_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Operator not permitted: {type(node.op).__name__}")
        left  = _eval_node(node.left,  depth + 1)
        right = _eval_node(node.right, depth + 1)
        result = op_fn(left, right)  # type: ignore[operator]
        if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
            raise ValueError("Result is undefined (NaN or Infinity).")
        if abs(result) > _MAX_RESULT_MAGNITUDE:
            raise ValueError("Result magnitude exceeds the allowed limit.")
        return result

    if isinstance(node, ast.UnaryOp):
        op_fn = _ALLOWED_UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unary operator not permitted: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand, depth + 1))  # type: ignore[operator]

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


class CalculatorTool:
    """
    Safely evaluates simple arithmetic expressions using AST parsing.

    Security model:
      1. Input is validated against a strict character-whitelist regex.
      2. The expression is parsed into an AST via ast.parse(mode='eval') —
         eval() is never called.
      3. The AST walker permits ONLY numeric literals and four arithmetic
         operators (+, -, *, /).  Any other node type raises an error.
      4. Result magnitude is bounded to prevent integer-overflow abuse.
      5. All exceptions are caught and returned as a failed ToolResult.
    """

    name = "calculator"
    description = "Evaluates arithmetic expressions, e.g. '3 * (4 + 2) / 2'."

    def run(self, expression: str) -> ToolResult:
        expr = expression.strip()
        if not _SAFE_EXPR_RE.match(expr):
            return ToolResult(
                tool_name=self.name,
                input=expr,
                output="",
                success=False,
                error="Expression contains disallowed characters. "
                "Only digits and + - * / ( ) . are permitted.",
            )
        try:
            tree = ast.parse(expr, mode="eval")
            result = _eval_node(tree)
            return ToolResult(
                tool_name=self.name,
                input=expr,
                output=str(result),
                success=True,
            )
        except ZeroDivisionError:
            return ToolResult(
                tool_name=self.name,
                input=expr,
                output="",
                success=False,
                error="Division by zero.",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                input=expr,
                output="",
                success=False,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Fake Search (in-memory knowledge base)
# ---------------------------------------------------------------------------

_KNOWLEDGE_BASE: dict[str, str] = {
    "python": (
        "Python is a high-level, general-purpose programming language "
        "that emphasises readability and simplicity."
    ),
    "llm": (
        "Large Language Models (LLMs) are deep neural networks, typically "
        "Transformer-based, trained on massive text corpora to predict and "
        "generate natural language."
    ),
    "transformer": (
        "The Transformer architecture relies on self-attention mechanisms to "
        "model relationships between all tokens in a sequence simultaneously, "
        "enabling parallelisation during training."
    ),
    "tokenization": (
        "Tokenization converts raw text into discrete units (tokens) that a "
        "neural network can process. Common strategies include Byte-Pair "
        "Encoding (BPE) and WordPiece."
    ),
    "temperature": (
        "Temperature is a scalar applied to logits before the softmax. "
        "Low values sharpen the distribution (more deterministic); high values "
        "flatten it (more random / creative)."
    ),
    "softmax": (
        "Softmax normalises a vector of real numbers into a probability "
        "distribution where all values are positive and sum to 1."
    ),
    "docker": (
        "Docker packages applications and their dependencies into portable "
        "containers, ensuring consistent behaviour across different "
        "host environments."
    ),
    "agent": (
        "An AI agent combines reasoning, memory, and tool use to autonomously "
        "solve multi-step tasks without explicit per-step instructions."
    ),
    "reasoning": (
        "Chain-of-thought reasoning prompts a language model to produce "
        "intermediate steps before giving a final answer, improving accuracy "
        "on complex tasks."
    ),
    "attention": (
        "Attention is a mechanism that allows a model to focus on the most "
        "relevant parts of the input when producing each output token."
    ),
    "embedding": (
        "Embeddings are dense vector representations of tokens or sentences "
        "that capture semantic relationships in a continuous space."
    ),
    "nlp": (
        "Natural Language Processing (NLP) is the subfield of AI concerned "
        "with enabling computers to understand, interpret, and generate "
        "human language."
    ),
}


class FakeSearchTool:
    """
    Keyword-based retrieval from a small in-memory knowledge base.

    Matching is bidirectional: the query may contain a keyword, or a keyword
    may be a substring of the query.  Multiple matches are joined with ' | '.
    """

    name = "search"
    description = "Searches an in-memory knowledge base for topic summaries."

    def run(self, query: str) -> ToolResult:
        q = query.lower().strip()
        hits = [
            text
            for keyword, text in _KNOWLEDGE_BASE.items()
            if keyword in q or q in keyword
        ]
        if hits:
            return ToolResult(
                tool_name=self.name,
                input=query,
                output=" | ".join(hits),
                success=True,
            )
        return ToolResult(
            tool_name=self.name,
            input=query,
            output=f"No results found for '{query}'.",
            success=False,
            error="No matching entries in the knowledge base.",
        )
