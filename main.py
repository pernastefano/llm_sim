"""
main.py — Entry point for the LLM Simulation Demo.

Usage:
    python main.py                          # runs default query
    python main.py "What is 42 * 7 + 15?"  # runs custom query

Output:
    - Prints the final answer to stdout.
    - Saves the full execution trace to llm_trace.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly from the project root without an install step.
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import LLMPipeline  # noqa: E402

TRACE_PATH = Path(__file__).parent / "llm_trace.json"

# A few representative queries — change or extend as you like.
EXAMPLE_QUERIES = [
    "What is 42 * 7 + 15?",
    "What is an LLM?",
    "Explain tokenization in NLP",
    "Calculate 100 / 4 + 3 * 2",
    "Tell me about the transformer architecture",
]


def main() -> None:
    print("=" * 64)
    print("  LLM Simulation Demo")
    print("=" * 64)

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = EXAMPLE_QUERIES[0]
        print(f"No query supplied — using default: '{query}'")
        print("Tip: python main.py <your question>\n")

    print(f"Query : {query}\n")

    pipeline = LLMPipeline()
    result = pipeline.run(query)

    print("Answer:")
    print("-" * 40)
    print(result.final_answer)
    print("-" * 40)
    print(f"\nTrace : {len(result.trace.steps)} steps recorded")

    result.trace.save(str(TRACE_PATH))
    print(f"Trace saved → {TRACE_PATH.name}")

    print()
    print("Explore the trace:")
    print("  • Static viewer  : python -m http.server 8000")
    print("                     then open http://localhost:8000/ui/viewer.html")
    print()
    print("Or use the full web UI (query + answer + trace in one place):")
    print("  • Web server     : python server.py")
    print("                     then open http://localhost:5000/")


if __name__ == "__main__":
    main()
