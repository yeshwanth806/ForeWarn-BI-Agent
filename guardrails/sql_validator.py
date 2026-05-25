"""
SQL safety validator — structural (AST) rather than surface (regex).

Companion code for Pattern A.3 of "Designing for Determinism: GenAI Inside a
Mature BI-Analytics Platform". See the article for the motivation; this file
shows the AST-walking checker referenced there.

Why a parser, not a regex?
  Consider:  SELECT EXTRACT(YEAR FROM t.created_at) FROM users t
  A regex that scans for "table after FROM" gets confused by the FROM inside
  the EXTRACT(...) function. A parser walks the tree and skips function
  bodies; it knows which FROM is a table clause and which isn't.

What the full validator confirms:
  - exactly one top-level statement
  - the first meaningful keyword is SELECT or WITH
  - no forbidden keywords (DROP, DELETE, INSERT, UPDATE, GRANT, ...) appear
    anywhere outside literal strings
  - every referenced table and column exists in the allowed schema

Extracted from production code and lightly cleaned for publication. The
helpers `_record` and `_is_subquery` are project-specific and outlined as
stubs below — replace with your own when porting.
"""

from sqlparse.sql import IdentifierList, Identifier, Function, Parenthesis, Where
from sqlparse.tokens import Keyword


# ---------------------------------------------------------------------
# Tree walker — the heart of the validator.
# ---------------------------------------------------------------------

def _walk(tokens, after_from_like):
    """Walk a parsed SQL token stream and record table refs after FROM/JOIN.

    `after_from_like` tracks whether we're currently in a position where an
    identifier should be treated as a table reference. We flip it on
    FROM/JOIN, flip it back on WHERE/GROUP/ORDER/HAVING/etc., and explicitly
    skip into function bodies (EXTRACT(... FROM col), etc.).
    """
    cur_after = after_from_like
    for tok in tokens:
        if isinstance(tok, Where):
            _walk(tok.tokens, False)
            cur_after = False
            continue

        # Never descend into function bodies — FROM inside `EXTRACT(... FROM
        # col)` and similar constructs is NOT a table clause.
        if isinstance(tok, Function):
            continue

        if tok.ttype is Keyword:
            up = tok.normalized.upper()
            first_word = up.split()[0] if up else ""
            if first_word == "FROM" or "JOIN" in up:
                cur_after = True
                continue
            if first_word in ("WHERE", "GROUP", "ORDER", "HAVING",
                              "LIMIT", "UNION", "ON"):
                cur_after = False

        if cur_after:
            if isinstance(tok, IdentifierList):
                for ident in tok.get_identifiers():
                    _record(ident)
            elif isinstance(tok, Identifier):
                _record(tok)
            elif isinstance(tok, Parenthesis):
                # Only treat as subquery if it begins with SELECT/WITH —
                # otherwise it's a function-call's arg list.
                if _is_subquery(tok):
                    _walk(tok.tokens, False)
        elif tok.is_group:
            if isinstance(tok, Parenthesis) and not _is_subquery(tok):
                continue
            _walk(tok.tokens, cur_after)


# ---------------------------------------------------------------------
# Helper stubs — replace with your own implementations.
# ---------------------------------------------------------------------

def _record(ident) -> None:
    """Record a table reference for later schema validation.

    In production this appends to a thread-local collection that the
    top-level validator inspects after `_walk` returns, then cross-checks
    against the allowed schema.
    """
    raise NotImplementedError("Wire this up to your collector.")


def _is_subquery(parenthesis) -> bool:
    """Return True if a Parenthesis starts with SELECT or WITH.

    Used to distinguish real subqueries from function-call arg lists.
    """
    raise NotImplementedError("Implement by inspecting the first meaningful token.")


# ---------------------------------------------------------------------
# Top-level entry point sketch — fill in to wrap the walker.
# ---------------------------------------------------------------------

def validate_sql(sql: str, allowed_schema) -> tuple[bool, list[str]]:
    """Top-level entry point. Returns (is_safe, errors).

    Sketch only — the full implementation parses `sql` with sqlparse,
    runs the keyword and statement-count checks, calls `_walk` to collect
    table references, then cross-checks them against `allowed_schema`.
    """
    raise NotImplementedError("Compose the parse, keyword, walk, and schema checks here.")
