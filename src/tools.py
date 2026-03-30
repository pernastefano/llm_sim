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
import datetime
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
    "rag": (
        "Retrieval-Augmented Generation (RAG) combines a retrieval step — "
        "fetching relevant documents from an external store — with a "
        "generative LLM so the model can answer questions using up-to-date "
        "or proprietary knowledge without retraining."
    ),
    "fine-tuning": (
        "Fine-tuning adapts a pre-trained model to a specific task or domain "
        "by continuing training on a smaller, curated dataset. Techniques "
        "such as LoRA and QLoRA reduce the number of trainable parameters to "
        "lower memory and compute requirements."
    ),
    "rlhf": (
        "Reinforcement Learning from Human Feedback (RLHF) aligns an LLM with "
        "human preferences by training a reward model on human comparisons "
        "and then optimising the LLM against that reward using PPO or similar "
        "RL algorithms."
    ),
    "hallucination": (
        "Hallucination occurs when an LLM generates plausible-sounding but "
        "factually incorrect or fabricated information. Mitigations include "
        "RAG, grounding outputs to retrieved sources, and self-consistency "
        "sampling."
    ),
    "context window": (
        "The context window is the maximum number of tokens an LLM can process "
        "in a single forward pass, covering both the prompt and the generated "
        "output. Larger windows (e.g. 128 k tokens) allow longer documents "
        "but increase memory usage quadratically for standard attention."
    ),
    "prompt engineering": (
        "Prompt engineering is the practice of crafting input text to elicit "
        "desired behaviour from an LLM. Techniques include few-shot examples, "
        "chain-of-thought instructions, role assignment, and output format "
        "constraints."
    ),
    "gpu": (
        "Graphics Processing Units (GPUs) accelerate deep learning by "
        "performing thousands of floating-point operations in parallel. "
        "Modern training clusters use specialised chips such as NVIDIA H100 "
        "or Google TPUs to handle the massive matrix multiplications required "
        "by Transformer models."
    ),
    "bert": (
        "BERT (Bidirectional Encoder Representations from Transformers) is a "
        "Transformer encoder pre-trained with masked language modelling. It "
        "produces rich contextual embeddings and is widely used for "
        "classification, NER, and question-answering tasks."
    ),
    "gpt": (
        "GPT (Generative Pre-trained Transformer) is a decoder-only Transformer "
        "trained with causal language modelling to predict the next token. "
        "Successive GPT versions (GPT-2, GPT-3, GPT-4) scaled parameters and "
        "data to achieve strong general-purpose generation."
    ),
    "vector database": (
        "A vector database stores high-dimensional embedding vectors and "
        "supports approximate nearest-neighbour (ANN) search, making it the "
        "standard retrieval backend for RAG systems. Examples include "
        "Pinecone, Weaviate, Qdrant, and pgvector."
    ),
    "neural network": (
        "A neural network is a computational model composed of layers of "
        "interconnected nodes (neurons). Each neuron applies a weighted sum "
        "followed by a non-linear activation function. Deep networks with many "
        "layers can learn hierarchical representations from raw data."
    ),
    "backpropagation": (
        "Backpropagation computes gradients of the loss with respect to every "
        "parameter by applying the chain rule from the output layer back to "
        "the input. These gradients are used by optimisers such as Adam to "
        "update the weights."
    ),
    "gradient descent": (
        "Gradient descent iteratively moves model parameters in the direction "
        "opposite to the gradient of the loss function. Variants such as SGD, "
        "Adam, and AdaFactor adapt the learning rate per parameter to speed "
        "up convergence."
    ),
    "overfitting": (
        "Overfitting occurs when a model learns the training data too closely "
        "and fails to generalise to new examples. Common remedies include "
        "dropout, weight decay (L2 regularisation), early stopping, and "
        "data augmentation."
    ),
    "benchmark": (
        "Benchmarks evaluate LLM capabilities on standardised tasks. Popular "
        "examples include MMLU (knowledge), HumanEval (coding), GSM8K (maths), "
        "and BIG-Bench Hard (complex reasoning). Results must be interpreted "
        "carefully due to data contamination risks."
    ),
    "multimodal": (
        "Multimodal models process and generate information across multiple "
        "modalities — text, images, audio, video. Examples include GPT-4o and "
        "Gemini Ultra, which accept interleaved image-text inputs and produce "
        "text (and sometimes image) outputs."
    ),
    "inference": (
        "LLM inference is the process of running a trained model to generate "
        "output tokens. Optimisation techniques include quantisation (INT8, "
        "INT4), KV-cache reuse, speculative decoding, and continuous batching "
        "to maximise GPU throughput."
    ),
    "quantization": (
        "Quantization reduces the numerical precision of model weights and "
        "activations (e.g. from FP32 to INT8 or INT4) to shrink model size "
        "and speed up inference with minimal accuracy loss. GPTQ and AWQ are "
        "popular post-training quantization methods for LLMs."
    ),
    "lora": (
        "LoRA (Low-Rank Adaptation) fine-tunes only a small set of low-rank "
        "weight matrices injected into the original layers, drastically "
        "reducing the number of trainable parameters. QLoRA combines LoRA "
        "with 4-bit quantization for consumer GPU fine-tuning."
    ),
    "prompt injection": (
        "Prompt injection is an attack where malicious text in user input or "
        "retrieved documents overrides the system prompt and hijacks LLM "
        "behaviour. Defences include strict output parsing, sandboxing tool "
        "calls, and privilege separation between system and user messages."
    ),
}


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class ClockTool:
    """
    Returns the current local date and time.

    No input is required; any value passed is ignored.
    """

    name = "clock"
    description = "Returns the current local date and time."

    def run(self, _input: str = "") -> ToolResult:
        now = datetime.datetime.now()
        output = now.strftime("The current time is %H:%M on %A, %B %d, %Y.")
        return ToolResult(
            tool_name=self.name,
            input=_input,
            output=output,
            success=True,
        )


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
