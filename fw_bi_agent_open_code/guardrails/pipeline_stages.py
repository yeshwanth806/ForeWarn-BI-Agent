"""
Stage Pipeline — viz-config generation with deterministic validators between stages.

Companion code for §4 of "Integrating AI into a Live BI Platform — The
Patterns That Actually Held Up". See the article for the architectural
context; this file shows the alias-contract validator (referenced in the
article) plus an outline of the three-stage pipeline that wraps it.

Why three stages, not one prompt:
  A single prompt that does layout + chart-type pick + dim/metric classify +
  SQL rewrite produces failures that retries don't fix — hallucinated columns,
  missing mandatory aliases, references to tables not in the source. Splitting
  the prompt into three narrower contracts, each followed by a deterministic
  validator, turns most of those failures into retry-once-then-fall-back-to-rules.

Why fall back to rules, not to more LLM:
  Two wrong answers from the same prompt is a signal to start afresh, not to
  keep spinning the wheel. A deterministic fallback that produces a
  degraded-but-valid config is almost always better than another retry.
"""

import re
from typing import Callable

import sqlparse
from sqlparse.sql import Identifier, IdentifierList
from sqlparse.tokens import DML, Keyword


# ---------------------------------------------------------------------
# Alias-contract validators (V1).
#
# The platform's viz config requires SQL to project columns named exactly
# `dim1_name`, `dim2_name`, ..., `metric1`, `metric2`, etc. Chart types each
# require a specific subset of these mandatory aliases.
# ---------------------------------------------------------------------

_DIM_ALIAS_RE    = re.compile(r"^dim\d+_name$")
_METRIC_ALIAS_RE = re.compile(r"^metric\d+$")
_ALIAS_PATTERN   = re.compile(r"^(dim\d+_name|metric\d+)$")


def validate_datasql(rewritten_sql, chart_type_id, source_column_universe):
    """V1: rewritten SQL structural validation against the alias contract."""
    errors = []
    parsed = parse_sql(rewritten_sql)
    if parsed.errors:
        return False, [f"rewritten SQL parse error: {e}" for e in parsed.errors]

    aliases = list(parsed.aliases)
    if not aliases:
        return False, ["rewritten SQL has no projected aliases"]

    # Each projection alias must match dim{n}_name or metric{n}.
    for a in aliases:
        if not _ALIAS_PATTERN.match(a):
            errors.append(
                f"projection alias '{a}' does not match dim{{n}}_name "
                f"or metric{{n}} convention"
            )

    # Chart's mandatory aliases all present.
    tmpl = chart_template(chart_type_id) or {}
    mandatory = tmpl.get("mandatory_fields", {}).get("datasql_aliases", [])
    missing = [a for a in mandatory if a not in aliases]
    if missing:
        errors.append(f"missing mandatory aliases for {chart_type_id}: {missing}")

    return (not errors), errors


# ---------------------------------------------------------------------
# SQL parsing — projection-alias collector (sqlparse).
#
# `validate_datasql` only needs the projected aliases of the SELECT clause,
# so a tokenizer (sqlparse) is the right tool here — unlike §1's safety
# validator, which needs a real AST (sqlglot). Different job, different tool.
# ---------------------------------------------------------------------

class ParsedSQL:
    """Minimal parse result: a list of `errors` and the projected `aliases`."""

    def __init__(self, errors: list[str], aliases: list[str]):
        self.errors = errors
        self.aliases = aliases


def _alias_of(identifier: Identifier) -> str:
    """The output name of one projection: its `AS` alias, else the real name."""
    return identifier.get_alias() or identifier.get_real_name() or ""


def parse_sql(sql: str) -> ParsedSQL:
    """Parse SQL and return a `ParsedSQL` with `.errors` and `.aliases`.

    Collects the output names projected by the (first) SELECT clause —
    everything between `SELECT` and `FROM`.
    """
    statements = sqlparse.parse(sql)
    if not statements:
        return ParsedSQL(["empty SQL"], [])
    stmt = statements[0]
    if stmt.get_type() != "SELECT":
        return ParsedSQL([f"expected SELECT, got {stmt.get_type()}"], [])

    aliases: list[str] = []
    in_projection = False
    for tok in stmt.tokens:
        if tok.ttype is DML and tok.value.upper() == "SELECT":
            in_projection = True
            continue
        if not in_projection:
            continue
        if tok.ttype is Keyword and tok.value.upper() == "FROM":
            break
        if isinstance(tok, IdentifierList):
            aliases.extend(_alias_of(i) for i in tok.get_identifiers()
                           if isinstance(i, Identifier))
        elif isinstance(tok, Identifier):
            aliases.append(_alias_of(tok))

    return ParsedSQL([], [a for a in aliases if a])


# ---------------------------------------------------------------------
# Chart-contract registry.
#
# Production loads this from the platform's chart registry; the demo ships a
# small representative subset. Each chart type names the aliases its SQL must
# project.
# ---------------------------------------------------------------------

_CHART_REGISTRY = {
    "bar":     {"mandatory_fields": {"datasql_aliases": ["dim1_name", "metric1"]}},
    "line":    {"mandatory_fields": {"datasql_aliases": ["dim1_name", "metric1"]}},
    "pie":     {"mandatory_fields": {"datasql_aliases": ["dim1_name", "metric1"]}},
    "scatter": {"mandatory_fields": {"datasql_aliases": ["metric1", "metric2"]}},
    "table":   {"mandatory_fields": {"datasql_aliases": []}},
}


def chart_template(chart_type_id):
    """Return the chart-type template dict (mandatory aliases, etc.), or None."""
    return _CHART_REGISTRY.get(chart_type_id)


# ---------------------------------------------------------------------
# Stage Pipeline orchestration.
#
# `run_stage` is the reusable control flow the article is about: draft with
# the LLM, validate deterministically, retry once, then fall back to rules.
# The LLM call itself is the only external boundary — it is injected as a
# callable so the orchestration runs and is testable without a model.
# ---------------------------------------------------------------------

def run_stage(llm_stage: Callable[[int], object],
              validator: Callable[[object], tuple[bool, list]],
              rules_fallback: Callable[[], object],
              *, max_retries: int = 1) -> tuple[object, str, list]:
    """Run one stage: LLM draft -> validate -> retry once -> rules fallback.

    `llm_stage(attempt)` is the external boundary (calls the model in
    production). `validator(output)` returns (ok, errors). `rules_fallback()`
    produces a deterministic degraded-but-valid output. Returns
    (output, source, errors) where source is "llm", "llm-retry", or
    "rules-fallback".
    """
    errors: list = []
    for attempt in range(max_retries + 1):
        output = llm_stage(attempt)
        ok, errors = validator(output)
        if ok:
            return output, ("llm" if attempt == 0 else "llm-retry"), []
    # Two wrong answers from the same prompt -> stop spinning, fall back.
    return rules_fallback(), "rules-fallback", errors


# --- Stage validators (deterministic) --------------------------------

def _validate_intent(intent) -> tuple[bool, list]:
    if not isinstance(intent, dict):
        return False, ["intent must be a dict"]
    if not intent.get("chart_types"):
        return False, ["intent missing chart_types"]
    return True, []


def _validate_classify(classes, source_columns) -> tuple[bool, list]:
    if not isinstance(classes, dict):
        return False, ["classify must map column -> role"]
    errs = [f"unclassified column: {c}" for c in source_columns if c not in classes]
    # Reject hallucinated columns too — a classification the LLM invented for a
    # column not in the source would otherwise pass and propagate downstream.
    errs += [f"unknown column classified: {c}" for c in classes if c not in source_columns]
    errs += [f"column {c} has invalid role {r!r}"
             for c, r in classes.items() if r not in ("dimension", "metric")]
    return (not errs), errs


# --- Deterministic fallbacks -----------------------------------------

_METRIC_HINTS = ("amount", "total", "count", "sum", "qty", "quantity",
                 "price", "revenue", "value")


def _fallback_intent() -> dict:
    return {"layout": "single", "chart_types": ["table"]}


def _fallback_classify(source_columns) -> dict:
    """Name-based rule: a measure-looking name is a metric, else a dimension."""
    return {c: ("metric" if any(h in c.lower() for h in _METRIC_HINTS)
                else "dimension")
            for c in source_columns}


def _fallback_rewrite(classes: dict) -> str:
    """Project classified columns onto the alias contract; metrics get SUM()."""
    dims = [c for c, r in classes.items() if r == "dimension"]
    metrics = [c for c, r in classes.items() if r == "metric"]
    projections = [f"{c} AS dim{i}_name" for i, c in enumerate(dims, 1)]
    projections += [f"SUM({c}) AS metric{i}" for i, c in enumerate(metrics, 1)]
    select = ", ".join(projections) or "1 AS dim1_name"
    sql = f"SELECT {select} FROM source"
    if dims and metrics:
        sql += " GROUP BY " + ", ".join(f"dim{i}_name" for i in range(1, len(dims) + 1))
    return sql


def run_viz_config_pipeline(intent_stage: Callable[[int], object],
                            classify_stage: Callable[[int], object],
                            rewrite_stage: Callable[[int], object],
                            *, source_columns, chart_type_id,
                            max_retries: int = 1) -> dict:
    """Three stages — intent -> classify -> rewrite — each gated by a validator.

    The three `*_stage` callables are the LLM-backed boundary. Everything
    else — validation, retry, and the deterministic fallbacks — is what the
    article is about, and runs without a model. Returns a validated viz
    config; `_sources` records whether each stage came from the LLM or a
    deterministic fallback.
    """
    intent, intent_src, _ = run_stage(
        intent_stage, _validate_intent, _fallback_intent,
        max_retries=max_retries)

    classes, classify_src, _ = run_stage(
        classify_stage,
        lambda c: _validate_classify(c, source_columns),
        lambda: _fallback_classify(source_columns),
        max_retries=max_retries)

    datasql, rewrite_src, _ = run_stage(
        rewrite_stage,
        lambda s: validate_datasql(s, chart_type_id, source_columns),
        lambda: _fallback_rewrite(classes),
        max_retries=max_retries)

    return {
        "layout": intent,
        "columns": classes,
        "datasql": datasql,
        "_sources": {"intent": intent_src, "classify": classify_src,
                     "rewrite": rewrite_src},
    }
