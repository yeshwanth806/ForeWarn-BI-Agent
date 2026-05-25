"""
Stage Pipeline — viz-config generation with deterministic validators between stages.

Companion code for Pattern A.2 of "Designing for Determinism: GenAI Inside a
Mature BI-Analytics Platform". See the article for the architectural context;
this file shows the V1 alias-contract validator (referenced in the article)
plus an outline of the three-stage pipeline that wraps it.

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
# Helper stubs — replace with your own implementations.
# ---------------------------------------------------------------------

def parse_sql(sql):
    """Parse SQL and return an object exposing `.errors` and `.aliases`.

    Production implementation uses sqlparse plus a thin wrapper that
    collects projection aliases from the SELECT clause.
    """
    raise NotImplementedError("Wire up to your SQL parser of choice.")


def chart_template(chart_type_id):
    """Return the chart-type template dict (mandatory aliases, etc.).

    Production loads this from the platform's chart-contract registry.
    """
    raise NotImplementedError("Load from your chart contract registry.")


# ---------------------------------------------------------------------
# Stage Pipeline orchestration (outline).
#
# The real orchestration sits inside the Orchestrator and is project-
# specific. The shape below shows the contract: each stage has its own
# prompt, its own deterministic validator, and a retry-then-fall-back-
# to-rules policy.
# ---------------------------------------------------------------------

def run_viz_config_pipeline(user_intent, dataset_metadata, *, max_retries=1):
    """Three-stage pipeline: intent -> classify -> rewrite, each gated by a validator.

    Returns a validated viz config, or a deterministic-fallback config if
    the LLM stages can't produce a valid one within `max_retries`.
    """
    # Stage 1: intent (layout + chart types)
    #   - call LLM with the intent prompt
    #   - validate against the layout schema
    #   - retry once on failure; on second failure, fall back to deterministic layout rules
    #
    # Stage 2: classify (column -> dimension or metric)
    #   - call LLM with the classify prompt
    #   - validate every classification is in {dimension, metric} and covers all needed columns
    #   - retry once; on second failure, fall back to a rules-based classifier
    #     ("unknown columns are dropped, unknown metrics aggregate as SUM")
    #
    # Stage 3: rewrite (SQL -> alias contract)
    #   - call LLM with the rewrite prompt
    #   - validate with `validate_datasql` above
    #   - retry once; on second failure, fall back to a deterministic rewriter
    raise NotImplementedError("Wire to your Orchestrator and prompt registry.")
