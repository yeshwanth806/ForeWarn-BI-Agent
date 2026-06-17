"""
Runnable demo for §5 — the Fallback Chain (cooldowns, stickiness, override).

Run it:
    python demo/demo_fallback_chain.py

It drives `pick_model_chain` through four scenarios using dummy model IDs —
no providers, no API keys, no network. Failures are simulated by calling
`record_cooldown` directly, exactly as the Orchestrator would on a 503.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reliability import fallback_chain as fc
from reliability.fallback_chain import (
    pick_model_chain, record_cooldown, stick_session_to_model,
)

# Three dummy models — shape matches the `available` parameter.
MODELS = [
    {"id": "gemini-demo", "provider": "google"},
    {"id": "gpt-demo",    "provider": "openai"},
    {"id": "claude-demo", "provider": "anthropic"},
]


def _reset() -> None:
    """Clear module-level cooldown/stickiness state between scenarios."""
    fc._model_cooldowns.clear()
    fc._session_model.clear()


def check(label: str, got, expected) -> bool:
    ok = got == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    print(f"        got      : {got}")
    print(f"        expected : {expected}\n")
    return ok


def main() -> int:
    results = []

    # 1. Healthy: primary first, then one fallback (MAX_MODEL_ATTEMPTS == 2).
    _reset()
    results.append(check(
        "healthy — primary leads, capped at MAX_MODEL_ATTEMPTS",
        pick_model_chain("s1", "gemini-demo", MODELS),
        ["gemini-demo", "gpt-demo"],
    ))

    # 2. Primary is cooling: it is skipped, the next healthy models step up.
    _reset()
    record_cooldown("gemini-demo")            # simulate a 503 on the primary
    results.append(check(
        "primary cooling — skipped, healthy models step up",
        pick_model_chain("s2", "gemini-demo", MODELS),
        ["gpt-demo", "claude-demo"],
    ))

    # 3. Session stickiness: a prior success pins the session's model.
    _reset()
    stick_session_to_model("s3", "gpt-demo")  # gpt-demo succeeded earlier
    results.append(check(
        "stickiness — sticky model leads even when 'primary' differs",
        pick_model_chain("s3", "gemini-demo", MODELS),
        ["gpt-demo", "gemini-demo"],
    ))

    # 4. Everything cooling: override returns a non-empty chain anyway.
    _reset()
    for m in MODELS:
        record_cooldown(m["id"])
    chain = pick_model_chain("s4", "gemini-demo", MODELS)
    ok = (len(chain) > 0 and len(chain) <= fc.MAX_MODEL_ATTEMPTS)
    print(f"[{'PASS' if ok else 'FAIL'}] all cooling — override still answers")
    print(f"        got      : {chain}")
    print(f"        expected : non-empty, len <= {fc.MAX_MODEL_ATTEMPTS}\n")
    results.append(ok)

    # 5. Cooldown expiry: an expired cooldown is pruned and the model returns.
    _reset()
    record_cooldown("gpt-demo", seconds=-1)   # already expired
    chain = pick_model_chain("s5", "gemini-demo", MODELS)
    ok = "gpt-demo" in chain
    print(f"[{'PASS' if ok else 'FAIL'}] expired cooldown is pruned, model is eligible again")
    print(f"        got      : {chain}")
    print(f"        expected : contains 'gpt-demo'\n")
    results.append(ok)

    passed = sum(results)
    total = len(results)
    print(f"{passed}/{total} scenarios behaved as expected.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
