"""
Agent prompt builder for the learning assistant.

This module owns everything the LLM sees:
  - system role & persona
  - output format contract (learning_path JSON schema)
  - policy rules (staging, feedback, node types)
  - context assembly

The worker infrastructure (polling, heartbeat, retry, callbacks) lives
in the surrounding runner and is NOT this module's concern.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Output format contract
# ---------------------------------------------------------------------------

LEARNING_PATH_SCHEMA = """
{
  "learning_path": {
    "title": "<string, ≤50 chars>",
    "goal": "<string, one sentence describing the end state>",
    "nodes": [
      {
        "node_code": "<unique snake_case id, e.g. step_01>",
        "title": "<string, ≤60 chars>",
        "node_type": "<lesson | checkpoint | practice | resource | other>",
        "description": "<string, 1-3 sentences>",
        "est_minutes": <integer, realistic time estimate>,
        "sort_no": <integer, 1-based>,
        "parent_node_code": "<node_code of parent, or null if top-level>"
      }
    ]
  }
}
"""

NODE_TYPE_GUIDE = """
- lesson      : new concept or knowledge unit to learn
- checkpoint  : self-assessment or quiz to verify understanding
- practice    : hands-on exercise, coding task, or project
- resource    : external reading, video, or reference material
- other       : anything that doesn't fit the above
"""


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a learning path designer for a mobile learning app.
Your job is to turn a learner's question or goal into a structured, \
actionable learning path they can follow step by step on their phone.

Principles:
1. Be concrete — every node must have a clear deliverable or outcome.
2. Be realistic — estimate time honestly; mobile learners have short sessions.
3. Be progressive — order nodes so each one builds on the previous.
4. Be concise — titles ≤60 chars, descriptions 1-3 sentences.
5. Prefer 5-12 nodes per path; split large topics into sub-paths rather than \
   creating an overwhelming list.
"""


# ---------------------------------------------------------------------------
# Policy rules
# ---------------------------------------------------------------------------

BASE_POLICY = """\
- Always output a single JSON object matching the schema below. No prose outside the JSON.
- Use `context_json` only as supporting context; do not assume it is complete or always present.
- Include at least one `checkpoint` node after every 3 `lesson` nodes.
- Include at least one `practice` node per major topic.
- `sort_no` must be unique and sequential starting from 1.
- `node_code` must be unique within the path, snake_case, e.g. "intro_python", "step_03".
- `est_minutes` must be a positive integer; use null only if genuinely unknown.
"""

FEEDBACK_POLICY = """\
- This is a REGENERATE request. The learner gave feedback on the previous answer.
- Keep parts the learner found useful; explicitly fix the issues they raised.
- Do not simply reorder nodes — make substantive changes based on the feedback.
"""

REGEN_RATING_HINTS = {
    "dislike": "The learner disliked the previous response. Rethink the structure significantly.",
    "like": "The learner liked parts of it but wants improvements. Preserve what worked.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Context block
# ---------------------------------------------------------------------------

def _build_context_block(claim: dict[str, Any]) -> str:
    """Assemble the structured context the model needs to personalise the path."""
    parts: dict[str, Any] = {}

    if claim.get("conversation_id"):
        parts["conversation_id"] = claim["conversation_id"]
    if claim.get("task_id"):
        parts["task_id"] = claim["task_id"]
    if claim.get("frontend_request_id"):
        parts["frontend_request_id"] = claim["frontend_request_id"]

    # question metadata (e.g. subject, level, prior knowledge)
    meta = claim.get("question_meta_json")
    if isinstance(meta, dict) and meta:
        parts["question_meta"] = meta

    # Optional backend-provided context. The AI side stays stateless; backend owns memory.
    context_json = claim.get("context_json")
    if isinstance(context_json, dict) and context_json:
        parts["context_json"] = context_json

    # feedback context
    for key in ("feedback_id", "feedback_rating", "feedback_reason", "feedback_detail"):
        val = _text(claim.get(key))
        if val:
            parts[key] = val

    return _compact_json(parts)


# ---------------------------------------------------------------------------
# Policy block
# ---------------------------------------------------------------------------

def _build_policy_block(claim: dict[str, Any]) -> str:
    lines = [BASE_POLICY.strip()]

    feedback_rating = _text(claim.get("feedback_rating"))
    feedback_reason = _text(claim.get("feedback_reason"))
    feedback_detail = _text(claim.get("feedback_detail"))

    is_regen = bool(feedback_rating or feedback_reason or feedback_detail)
    if is_regen:
        lines.append(FEEDBACK_POLICY.strip())
        hint = REGEN_RATING_HINTS.get(feedback_rating)
        if hint:
            lines.append(f"Rating hint: {hint}")
        if feedback_reason:
            lines.append(f"Feedback reason: {feedback_reason}")
        if feedback_detail:
            lines.append(f"Feedback detail: {feedback_detail}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_prompt_messages(claim: dict[str, Any]) -> list[dict[str, str]]:
    """
    Build the messages list to send to the LLM.

    Args:
        claim: the task claim dict from /backend/tasks/claim, containing at minimum
               question_text, and optionally feedback_*, question_meta_json, etc.

    Returns:
        List of {"role": ..., "content": ...} dicts ready for the chat completions API.

    Raises:
        ValueError: if question_text is missing or blank.
    """
    question_text = _text(claim.get("question_text"))
    if not question_text:
        raise ValueError("claim is missing question_text")

    return [
        {
            "role": "system",
            "content": f"[ROLE]\n{SYSTEM_PROMPT.strip()}",
        },
        {
            "role": "system",
            "content": f"[OUTPUT FORMAT]\nRespond with exactly this JSON structure:\n{LEARNING_PATH_SCHEMA.strip()}",
        },
        {
            "role": "system",
            "content": f"[NODE TYPES]\n{NODE_TYPE_GUIDE.strip()}",
        },
        {
            "role": "system",
            "content": f"[POLICY]\n{_build_policy_block(claim)}",
        },
        {
            "role": "system",
            "content": f"[CONTEXT]\n{_build_context_block(claim)}",
        },
        {
            "role": "user",
            "content": question_text,
        },
    ]
