"""Run a SEVOR AI quality corpus through the offline service evaluator.

Examples:
  python scripts/evaluate_chatbot_quality.py
  python scripts/evaluate_chatbot_quality.py --json
  python scripts/evaluate_chatbot_quality.py --baseline path/to/prior.json --json

The command never calls an LLM provider, creates tickets, mutates user data,
or reads production credentials.  It reports missing endpoint/provider review
as a limitation instead of silently converting it into a passing score.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.chatbot_evaluation import DEFAULT_CORPUS_PATH, evaluate_quality_corpus  # noqa: E402


def _fraction(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator}" if denominator else "n/a"


def _baseline_delta(current: dict, baseline: dict) -> dict[str, int | None]:
    """Compare only compatible recorded counters; never invent a baseline."""

    metrics = {
        "single_turn.expected_intent_matches": ("single_turn", "expected_intent_matches"),
        "single_turn.guest_route_signal_matches": ("single_turn", "guest_route_signal_matches"),
        "multi_turn.expected_intent_matches": ("multi_turn", "expected_intent_matches"),
        "multi_turn.follow_up_context_signal_matches": ("multi_turn", "follow_up_context_signal_matches"),
    }
    comparison: dict[str, int | None] = {}
    for name, (section, key) in metrics.items():
        before = baseline.get(section, {}).get(key)
        after = current.get(section, {}).get(key)
        comparison[name] = after - before if isinstance(before, int) and isinstance(after, int) else None
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH, help="Path to the held-out evaluation JSON.")
    parser.add_argument("--baseline", type=Path, help="Optional prior JSON report produced by this command.")
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report.")
    parser.add_argument("--output", type=Path, help="Write the complete JSON report to this explicit path.")
    args = parser.parse_args()

    result = evaluate_quality_corpus(args.corpus)
    if args.baseline:
        with args.baseline.open(encoding="utf-8") as baseline_file:
            result["baseline_comparison"] = {
                "baseline_path": str(args.baseline),
                "deltas": _baseline_delta(result, json.load(baseline_file)),
            }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    single = result["single_turn"]
    multi = result["multi_turn"]
    print("SEVOR AI offline service evaluation")
    print(f"Provider readiness: {result['provider_readiness']} (provider called: {result['provider_called']})")
    print(
        "Single-turn service calls: "
        f"{single['service_calls_completed']}/{single['total']} "
        f"(failures: {len(single['service_call_failures'])})"
    )
    print(
        "Single-turn exact expected intents: "
        + _fraction(single["expected_intent_matches"], single["expected_intent_cases"])
    )
    print(
        "Guest-route signals (non-authenticated cases only): "
        + _fraction(single["guest_route_signal_matches"], single["guest_route_signal_cases"])
    )
    print(
        "Security-refusal routes: "
        + _fraction(single["security_refusal_matches"], single["security_refusal_expected"])
    )
    print(
        "Sensitive-data safety routes: "
        + _fraction(single["sensitive_data_safety_matches"], single["sensitive_data_safety_expected"])
    )
    print(f"Authenticated endpoint cases deferred: {single['authenticated_endpoint_cases']}")
    print(
        "Multi-turn exact expected intents: "
        + _fraction(multi["expected_intent_matches"], multi["expected_intent_cases"])
    )
    print(
        "Multi-turn follow-up signals: "
        + _fraction(multi["follow_up_context_signal_matches"], multi["follow_up_context_cases"])
    )
    print("For full observations, provider status, and limitations: rerun with --json.")
    if args.output:
        print(f"Full JSON report written to: {args.output}")
    return 1 if single["service_call_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
