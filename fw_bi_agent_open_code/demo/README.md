# Runnable demos

Self-contained scripts that exercise the code from the article — **no API keys, no database, no network.** Each prints `PASS`/`FAIL` per case and exits non-zero if anything misbehaves.

## Setup

```bash
pip install sqlglot          # only the SQL-validator demo needs this
```

(`demo_fallback_chain.py` uses the standard library only.)

## Run

From the repo root:

```bash
python demo/demo_sql_validator.py     # §1 — structural SQL validation
python demo/demo_fallback_chain.py    # §5 — cooldowns, stickiness, override
```

## What each demo shows

### `demo_sql_validator.py` (§1)
Feeds nine queries through `validate_sql` against a tiny `{table: columns}` schema and checks each is accepted or rejected for the right reason:

- plain `SELECT`, a `JOIN`, and a `WITH` (CTE) of known columns — **accepted**
- `EXTRACT(YEAR FROM t.created_at)` — **accepted** (the `FROM` inside a function fools a regex "table after FROM" check, but not the AST walk)
- `DELETE`, `DROP`, a hallucinated column, an unknown table, and two stacked statements — **rejected**

### `demo_fallback_chain.py` (§5)
Drives `pick_model_chain` through five scenarios with three dummy model IDs. Provider failures are simulated by calling `record_cooldown` directly, exactly as the Orchestrator does on a 503:

1. **Healthy** — primary leads, chain capped at `MAX_MODEL_ATTEMPTS`.
2. **Primary cooling** — it's skipped; healthy models step up.
3. **Stickiness** — a prior success pins the session's model ahead of `primary`.
4. **Everything cooling** — the last-resort override still returns an answer.
5. **Cooldown expiry** — an expired cooldown is pruned and the model is eligible again.

## Note

These demos cover the two patterns that run without external services. The BYOK agent-cache (§6) and telemetry schema (§5) demos would require a fake LLM/agent and a database respectively, and are intentionally not included here.
