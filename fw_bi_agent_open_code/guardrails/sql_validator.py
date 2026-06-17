"""
SQL safety validator — structural (real AST) rather than surface (regex).

Companion code for §1 of "Integrating AI into a Live BI Platform — The
Patterns That Actually Held Up". See the article for the motivation; this
file shows the AST-based checker referenced there.

Why a real parser — not a regex, and not just a tokenizer?
  Consider:  SELECT EXTRACT(YEAR FROM t.created_at) FROM users t
  A regex that scans for "table after FROM" is fooled by the FROM inside
  EXTRACT(...). Our first cut reached for `sqlparse`, but sqlparse only
  *tokenizes* — it hands back a flat token stream, so telling the FROM
  inside a function apart from a real table clause still meant hand-rolling
  stateful walk logic that was easy to get wrong.

  We moved to `sqlglot`, which builds a true Abstract Syntax Tree. Each
  construct becomes a typed node: EXTRACT(...) is a function node, a table
  reference is an `exp.Table`, a column is an `exp.Column`. Validation is
  then node-type checks over the tree instead of token bookkeeping.

What the validator confirms:
  - exactly one top-level statement
  - the statement is a read (SELECT / WITH / UNION), not DDL/DML
  - no forbidden node types (Drop, Delete, Insert, Update, ...) anywhere
  - every referenced table and column exists in the allowed schema

Extracted from production code and lightly cleaned for publication. The
schema-lookup helpers below are implemented in full against a simple
{table: columns} schema; the only piece simplified for portability is
table-alias resolution (noted inline). See `demo/demo_sql_validator.py`
for a runnable example.
"""

import sqlglot
from sqlglot import exp

# sqlglot is dialect-aware; parsing with the warehouse's dialect avoids
# false rejects on valid platform-specific SQL.
DIALECT = "postgres"

# Anything that mutates or administers is rejected wherever it appears in
# the tree — not just at the top level.
FORBIDDEN_NODES = (
    exp.Drop, exp.Delete, exp.Insert, exp.Update,
    exp.Alter, exp.Create, exp.Grant, exp.Command,
)


def validate_sql(sql: str, allowed_schema) -> tuple[bool, list[str]]:
    """Return (is_safe, errors). Structural validation over a sqlglot AST."""
    errors: list[str] = []

    # 1. Parse. Exactly one statement — sqlglot.parse returns a list of roots.
    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s]
    except sqlglot.errors.ParseError as exc:
        return False, [f"unparseable SQL: {exc}"]
    if len(statements) != 1:
        return False, ["exactly one statement allowed"]
    root = statements[0]

    # 2. Must be a read. SELECT, a UNION of selects, or a WITH-wrapped select.
    if not isinstance(root, (exp.Select, exp.Union, exp.With)):
        return False, [f"only SELECT/WITH queries allowed, got {type(root).__name__}"]

    # 3. No forbidden node types anywhere in the tree (defends against a
    #    mutation smuggled inside a CTE or subquery).
    for node in root.find_all(*FORBIDDEN_NODES):
        errors.append(f"forbidden operation: {type(node).__name__}")

    # 4. Every table and column must exist in the allowed schema. find_all
    #    yields only real table/column nodes — the FROM inside EXTRACT(...)
    #    never surfaces as a table, which is the whole point of walking an
    #    AST instead of scanning tokens.
    #
    #    Names introduced by WITH ... AS (...) are query-local, not schema
    #    tables, so collect them first and exempt them from the schema check.
    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        if table.name.lower() in cte_names:
            continue
        if not _table_allowed(table.name, allowed_schema):
            errors.append(f"unknown table: {table.name}")
    for column in root.find_all(exp.Column):
        if not _column_allowed(column, allowed_schema):
            errors.append(f"unknown column: {column.sql()}")

    return (not errors), errors


# ---------------------------------------------------------------------
# Helper stubs — replace with your own schema-lookup implementations.
# ---------------------------------------------------------------------

def _table_allowed(table_name: str, allowed_schema) -> bool:
    """Return True if `table_name` is in the allowed schema (case-insensitive)."""
    return table_name.lower() in {t.lower() for t in allowed_schema}


def _column_allowed(column, allowed_schema) -> bool:
    """Confirm a referenced column exists in the allowed schema.

    Demo simplification: an unqualified column is accepted if it exists in
    *any* allowed table; a qualified column (`t.created_at`) is checked
    against its table when that table name is known. Production first
    resolves the column's table *alias* to a concrete table, then checks
    only that table's columns — alias resolution is the project-specific
    part and is omitted here for portability.
    """
    col_name = column.name.lower()
    table_ref = (column.table or "").lower()

    # Qualified by a real table name we know: check that table only.
    for tname, cols in allowed_schema.items():
        if tname.lower() == table_ref:
            return col_name in {c.lower() for c in cols}

    # Unqualified, or qualified by an alias we don't resolve here: accept if
    # the column exists in any allowed table.
    all_cols = {c.lower() for cols in allowed_schema.values() for c in cols}
    return col_name in all_cols
