"""
Fallback Chain — model cooldown, session stickiness, last-resort override.

Companion code for Pattern B.5 of "Designing for Determinism: GenAI Inside a
Mature BI-Analytics Platform". See the article for the architectural context;
this file shows the chain-construction logic referenced there.

Behavior summary:
  - Cooldowns:   a failed model is skipped for COOLDOWN_SECONDS (configurable).
  - Stickiness:  a user's session stays locked to its working model for the
                 whole conversation, so the user doesn't silently swap models
                 mid-conversation as cooldowns expire.
  - Override:    if every model in the chain is cooling simultaneously, the
                 override ignores cooldowns for that one turn so the user
                 still gets an answer.

Extracted from production code in ForeWarn-BI-Agent and lightly cleaned for
publication. Integration with the Orchestrator (where cooldowns are recorded
on failure and the session model is set on first success) is project-specific.
"""

import time

# Module-level state. In production these are protected by appropriate locks
# at the call sites; lock plumbing is omitted here for clarity.
_model_cooldowns: dict[str, float] = {}   # model_id -> cooldown-expiry epoch
_session_model: dict[str, str] = {}       # session_id -> sticky model_id

# Tunables.
MAX_MODEL_ATTEMPTS = 3          # cap on chain length per turn
COOLDOWN_SECONDS = 10 * 60      # ten minutes; configurable per deployment

# The provider catalogue. In production this is loaded from config; the shape
# here matches the `available` parameter passed in below.
ALLOWED_MODELS: list[dict] = [
    # {"id": "gemini-...", "provider": "google"},
    # {"id": "gpt-...",    "provider": "openai"},
    # {"id": "claude-...", "provider": "anthropic"},
]


def pick_model_chain(session_id: str, primary: str,
                     available: list[dict] | None = None,
                     default_fallback: str = "") -> list[str]:
    """Return up to MAX_MODEL_ATTEMPTS model IDs, skipping those in cooldown."""
    now = time.time()
    for mid, exp in list(_model_cooldowns.items()):
        if exp <= now:
            _model_cooldowns.pop(mid, None)
    cooling = set(_model_cooldowns.keys())

    avail = available if available is not None else ALLOWED_MODELS
    all_ids = [m["id"] for m in avail] or ([primary] if primary else [])
    effective_primary = _session_model.get(session_id) or primary or default_fallback

    chain: list[str] = []

    def _add(mid: str) -> None:
        if mid and mid not in chain and mid not in cooling:
            chain.append(mid)

    _add(effective_primary)
    for mid in all_ids:
        if len(chain) >= MAX_MODEL_ATTEMPTS:
            break
        _add(mid)

    if not chain:  # everything cooling — override for this turn
        chain = [effective_primary] + [m for m in all_ids if m != effective_primary]
        chain = [m for m in chain if m]
    return chain[:MAX_MODEL_ATTEMPTS]


def record_cooldown(model_id: str, seconds: int = COOLDOWN_SECONDS) -> None:
    """Mark a model as cooling for `seconds` after a failed invocation."""
    if model_id:
        _model_cooldowns[model_id] = time.time() + seconds


def stick_session_to_model(session_id: str, model_id: str) -> None:
    """Lock a session to a model on first success — supports stickiness."""
    if session_id and model_id:
        _session_model.setdefault(session_id, model_id)


def clear_session_stickiness(session_id: str) -> None:
    """Drop a session's sticky model — used when a session ends or resets."""
    _session_model.pop(session_id, None)
