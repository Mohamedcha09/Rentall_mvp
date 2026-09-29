"""Offline, service-level quality evaluation for the SEVOR AI chatbot.

This module deliberately exercises the same ``support_ai`` functions used by
the chat routes.  It does *not* pretend to be a production/provider test:
authenticated account tools, ticket persistence, and human handoff state need
an isolated database and the real endpoint.  The result therefore separates
what was executed from what still needs endpoint or human review.

It is kept outside the request path so evaluation fixtures can never affect
customer routing or approved support knowledge.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
import json

from app.support_ai import (
    IntentAnalysis,
    analyze_support_intent,
    classify_conversation_turn,
    create_guest_ai_answer,
    guest_requires_sign_in,
    is_handoff_request,
    provider_operating_mode,
    retrieve_knowledge,
)


DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "chatbot_quality_evaluation.json"

# A guest cannot safely execute account tools or create a durable human
# handoff.  These fixture routes are still exercised up to their server-side
# *routing gate*, and are separately counted as requiring authenticated
# endpoint verification rather than marked as a false pass.
_AUTHENTICATED_ENDPOINT_ROUTES = {
    "safe_tool",
    "safe_tool_or_clarify",
    "safe_tool_or_handoff",
    "safe_tool_or_knowledge",
    "safe_tool_or_privacy_safe_limit",
    "clarify_or_safe_tool",
    "clarify_or_safe_limit",
    "handoff",
    "handoff_state",
}


def load_quality_corpus(path: Path | str = DEFAULT_CORPUS_PATH) -> dict[str, Any]:
    """Load a quality corpus without changing any support state."""

    corpus_path = Path(path)
    with corpus_path.open(encoding="utf-8") as corpus_file:
        return json.load(corpus_file)


def _expected_routes(expected: dict[str, Any]) -> set[str]:
    """Split fixture alternatives, e.g. ``knowledge_or_clarify``."""

    route = str(expected.get("route") or "")
    return {part for part in route.split("_or_") if part}


def _expected_needs_authenticated_endpoint(expected: dict[str, Any]) -> bool:
    route = str(expected.get("route") or "")
    return any(candidate in _AUTHENTICATED_ENDPOINT_ROUTES for candidate in _expected_routes(expected))


def _route_observation(
    message: str,
    expected: dict[str, Any],
    *,
    metadata: dict[str, Any],
    answer: str,
) -> dict[str, Any]:
    """Record only facts that the guest service path actually establishes."""

    expected_routes = _expected_routes(expected)
    response_mode = str(metadata.get("response_mode") or "")
    conversation_role = str(metadata.get("conversation_role") or "")
    observed: set[str] = set()

    if conversation_role in {"greeting", "thanks", "password_clarification", "why_limited", "tried_steps"}:
        observed.add(conversation_role)
    if response_mode == "security_blocked":
        observed.add("security_refusal")
    if response_mode == "sensitive_data_safety":
        observed.add("sensitive_data_safety")
    if response_mode == "guest_sign_in_required":
        observed.add("guest_sign_in_required")
    if metadata.get("knowledge_ids"):
        observed.add("knowledge")
    if response_mode == "knowledge_gap":
        observed.add("safe_limit")
        observed.add("unknown_policy")
        if str(metadata.get("knowledge_gap") or "").startswith("privacy_"):
            observed.add("privacy_safe_limit")
    if conversation_role == "password_clarification":
        # The runtime uses a more informative internal label for the focused
        # reset-vs-change question; it is still the corpus's clarification
        # route, not a different answer behavior.
        observed.add("clarify")
    if is_handoff_request(message):
        # This confirms explicit-human language reaches the shared handoff
        # classifier.  The actual ticket transition is intentionally left to
        # the authenticated endpoint suite.
        observed.add("handoff_request_detected")

    expected_intent = expected.get("intent")
    actual_intents = tuple(metadata.get("intents") or ())
    intent_match = expected_intent is None or expected_intent in actual_intents
    route_match = bool(expected_routes & observed)
    requires_endpoint = _expected_needs_authenticated_endpoint(expected)

    return {
        "expected_route": expected.get("route"),
        "observed_route_signals": sorted(observed),
        "expected_intent": expected_intent,
        "actual_intents": list(actual_intents),
        "intent_match": intent_match,
        "guest_route_signal_match": route_match,
        "requires_authenticated_endpoint": requires_endpoint,
        "guest_request_was_safely_gated": bool(
            metadata.get("response_mode") == "guest_sign_in_required" or not guest_requires_sign_in(message)
        ),
        "response_mode": response_mode,
        "provider": metadata.get("provider"),
        "tool_names": list(metadata.get("tool_names") or ()),
        "knowledge_ids": list(metadata.get("knowledge_ids") or ()),
        "answer_present": bool((answer or "").strip()),
    }


def _assistant_history_message(
    analysis: IntentAnalysis,
    expected: dict[str, Any],
    knowledge_ids: Iterable[str],
) -> SimpleNamespace:
    """Build the minimal persisted metadata a real prior assistant turn uses.

    The fixture contains placeholders for preceding assistant turns.  We do
    not invent their prose; this helper models only the auditable route/tool
    metadata that ``support_ai`` reads to resolve the next short user turn.
    """

    expected_routes = _expected_routes(expected)
    expected_tool = expected.get("tool")
    tool_names = []
    if expected_tool == "current_user_verification":
        tool_names.append("get_my_verification_status")
    elif expected_tool == "current_user_booking_status":
        tool_names.append("get_my_booking_status")
    elif expected_tool == "current_user_payment_status":
        tool_names.append("get_my_payment_status")
    elif expected_tool == "current_owner_payout_status":
        tool_names.append("get_my_payout_status")
    elif expected_tool == "owned_listing_status":
        tool_names.append("get_my_listing_status")

    return SimpleNamespace(
        sender_role="assistant",
        metadata_json=json.dumps(
            {
                "intent": analysis.primary,
                "intents": list(analysis.intents),
                "tool_names": tool_names,
                # An unknown-policy answer is a deliberate information
                # boundary.  Its short “Why?” follow-up must remain attached
                # to that limitation rather than becoming a generic FAQ.
                "knowledge_gap": "policy_not_approved" if "unknown_policy" in expected_routes else None,
                "knowledge_ids": list(knowledge_ids),
            }
        ),
    )


def _evaluate_dialogue(dialogue: dict[str, Any]) -> dict[str, Any]:
    """Exercise real context analysis over the fixture's user turns."""

    history: list[SimpleNamespace] = []
    observations: list[dict[str, Any]] = []
    for turn in dialogue.get("turns", []):
        message = str(turn.get("message") or "")
        expected = dict(turn.get("expected") or {})
        # Fixture placeholders describe a prior system reply.  Metadata for
        # each actual user turn is appended below, so no placeholder prose is
        # ever injected into the support implementation.
        if message.startswith("<system under test"):
            continue
        analysis = analyze_support_intent(message, history=history)
        role = classify_conversation_turn(message, history=history, intent=analysis)
        knowledge = retrieve_knowledge(message, intent=analysis)
        expected_intent = expected.get("intent")
        expected_routes = _expected_routes(expected)
        continuation_ok = (
            "follow_up_context" not in expected_routes
            or analysis.from_context
            or role in {"why_limited", "tried_steps"}
        )
        observations.append(
            {
                "message": message,
                "expected_route": expected.get("route"),
                "expected_intent": expected_intent,
                "actual_intents": list(analysis.intents),
                "intent_match": expected_intent is None or expected_intent in analysis.intents,
                "from_context": analysis.from_context,
                "conversation_role": role,
                "continuation_signal_match": continuation_ok,
                "handoff_request_detected": is_handoff_request(message),
                "knowledge_ids": [entry.id for entry in knowledge],
                "requires_authenticated_endpoint": _expected_needs_authenticated_endpoint(expected),
            }
        )
        history.append(_assistant_history_message(analysis, expected, (entry.id for entry in knowledge)))

    expected_turns = [turn for turn in dialogue.get("turns", []) if not str(turn.get("message") or "").startswith("<system under test")]
    return {
        "id": dialogue.get("id"),
        "user_turns": len(expected_turns),
        "observations": observations,
        "intent_matches": sum(1 for row in observations if row["intent_match"]),
        "continuation_signal_matches": sum(1 for row in observations if row["continuation_signal_match"]),
        "authenticated_endpoint_turns": sum(1 for row in observations if row["requires_authenticated_endpoint"]),
    }


def evaluate_quality_corpus(path: Path | str = DEFAULT_CORPUS_PATH) -> dict[str, Any]:
    """Run the non-network service evaluation and return JSON-safe facts.

    Each single-turn case calls ``create_guest_ai_answer``.  This reaches the
    real normalization, role detection, deterministic/provider-gate routing,
    retrieval, source-grounded fallback, and safety checks.  It deliberately
    does not call a provider or use private test-user data.
    """

    corpus = load_quality_corpus(path)
    single_observations: list[dict[str, Any]] = []
    response_modes: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    failures: list[dict[str, str]] = []

    for case in corpus.get("single_turn_cases", []):
        message = str(case.get("message") or "")
        expected = dict(case.get("expected") or {})
        try:
            answer, metadata = create_guest_ai_answer(message)
            observation = _route_observation(message, expected, metadata=metadata, answer=answer)
            observation["id"] = case.get("id")
            observation["language"] = case.get("language")
            single_observations.append(observation)
            response_modes[str(metadata.get("response_mode") or "missing")] += 1
            providers[str(metadata.get("provider") or "missing")] += 1
        except Exception as exc:  # The report must expose, not hide, a failure.
            failures.append({"id": str(case.get("id")), "error": f"{type(exc).__name__}: {exc}"})

    dialogues = [_evaluate_dialogue(dialogue) for dialogue in corpus.get("multi_turn_dialogues", [])]
    expected_intent_rows = [row for row in single_observations if row["expected_intent"]]
    guest_route_rows = [row for row in single_observations if not row["requires_authenticated_endpoint"]]
    security_rows = [row for row in single_observations if row["expected_route"] == "security_refusal"]
    sensitive_rows = [row for row in single_observations if row["expected_route"] == "sensitive_data_safety"]
    dialogue_rows = [row for dialogue in dialogues for row in dialogue["observations"]]
    dialogue_intent_rows = [row for row in dialogue_rows if row["expected_intent"]]
    continuation_rows = [
        row
        for row in dialogue_rows
        if "follow_up_context" in _expected_routes({"route": row["expected_route"]})
    ]

    return {
        "schema_version": "1.0",
        "evaluation_kind": "offline_service_runtime",
        "corpus_path": str(Path(path)),
        "provider_readiness": provider_operating_mode(),
        "provider_called": any(provider == "openai" for provider in providers),
        "limits": {
            "provider": "No external provider is called by this evaluator; an unavailable provider is reported, not treated as a quality pass.",
            "authenticated_endpoint": "Private tools, persistent message order, ticket-state handoff, and server-side authorization require the isolated endpoint suite.",
            "answer_review": "The fixture's natural-language must/must_not notes still require human review for factual usefulness and style.",
        },
        "single_turn": {
            "total": len(corpus.get("single_turn_cases", [])),
            "service_calls_completed": len(single_observations),
            "service_call_failures": failures,
            "expected_intent_cases": len(expected_intent_rows),
            "expected_intent_matches": sum(1 for row in expected_intent_rows if row["intent_match"]),
            "guest_route_signal_cases": len(guest_route_rows),
            "guest_route_signal_matches": sum(1 for row in guest_route_rows if row["guest_route_signal_match"]),
            "authenticated_endpoint_cases": sum(1 for row in single_observations if row["requires_authenticated_endpoint"]),
            "security_refusal_expected": len(security_rows),
            "security_refusal_matches": sum(1 for row in security_rows if row["response_mode"] == "security_blocked"),
            "sensitive_data_safety_expected": len(sensitive_rows),
            "sensitive_data_safety_matches": sum(1 for row in sensitive_rows if row["response_mode"] == "sensitive_data_safety"),
            "response_modes": dict(sorted(response_modes.items())),
            "providers": dict(sorted(providers.items())),
            "observations": single_observations,
        },
        "multi_turn": {
            "dialogues": len(dialogues),
            "user_turns": len(dialogue_rows),
            "expected_intent_cases": len(dialogue_intent_rows),
            "expected_intent_matches": sum(1 for row in dialogue_intent_rows if row["intent_match"]),
            "follow_up_context_cases": len(continuation_rows),
            "follow_up_context_signal_matches": sum(1 for row in continuation_rows if row["continuation_signal_match"]),
            "authenticated_endpoint_turns": sum(dialogue["authenticated_endpoint_turns"] for dialogue in dialogues),
            "dialogues_detail": dialogues,
        },
    }
