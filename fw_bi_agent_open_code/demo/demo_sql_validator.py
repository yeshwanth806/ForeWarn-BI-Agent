"""
Runnable demo for §1 — the structural (sqlglot AST) SQL validator.

Run it:
    pip install sqlglot
    python demo/demo_sql_validator.py

It feeds a handful of queries through `validate_sql` against a tiny sample
schema and checks each one is accepted/rejected for the right reason —
including the EXTRACT(... FROM ...) case that fools a regex "table after
FROM" check but not an AST walk.

No API keys, no database, no network.
"""

import sys
from pathlib import Path

# Make the repo importable when run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guardrails.sql_validator import validate_sql

# Sample schema: table -> allowed columns.
SCHEMA = {
    "users": {"id", "email", "created_at", "country"},
    "orders": {"id", "user_id", "amount", "created_at"},
}

# (label, sql, expect_safe)
CASES = [
    ("plain SELECT of known columns",
     "SELECT id, email FROM users",
     True),

    ("EXTRACT(YEAR FROM col) — the regex-killer, must still pass",
     "SELECT EXTRACT(YEAR FROM t.created_at) AS yr FROM users t",
     True),

    ("JOIN across two known tables",
     "SELECT u.email, o.amount FROM users u JOIN orders o ON o.user_id = u.id",
     True),

    ("CTE (WITH) is still a read",
     "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent",
     True),

    ("DELETE — forbidden operation",
     "DELETE FROM users WHERE id = 1",
     False),

    ("DROP smuggled in — forbidden",
     "DROP TABLE users",
     False),

    ("hallucinated column not in schema",
     "SELECT id, ssn FROM users",
     False),

    ("unknown table",
     "SELECT id FROM customers",
     False),

    ("two statements stacked",
     "SELECT id FROM users; DROP TABLE users",
     False),
]


def main() -> int:
    failures = 0
    for label, sql, expect_safe in CASES:
        is_safe, errors = validate_sql(sql, SCHEMA)
        ok = (is_safe == expect_safe)
        failures += not ok
        status = "PASS" if ok else "FAIL"
        verdict = "ACCEPTED" if is_safe else "REJECTED"
        print(f"[{status}] {label}")
        print(f"        sql      : {sql}")
        print(f"        verdict  : {verdict} (expected {'ACCEPTED' if expect_safe else 'REJECTED'})")
        if errors:
            print(f"        reasons  : {errors}")
        print()

    total = len(CASES)
    print(f"{total - failures}/{total} cases behaved as expected.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
