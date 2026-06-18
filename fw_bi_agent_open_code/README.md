# Determinism Patterns for GenAI in Enterprise Analytics

Companion code for the article **[Integrating AI into a Live BI Platform — The Patterns That Actually Held Up](https://medium.com/@yeshwanthd806/integrating-ai-into-a-live-bi-platform-the-patterns-that-actually-held-up-71e348461642)**.

The article describes six production patterns we used to embed a conversational AI layer (ForeWarn-BI-Agent) on top of a governed enterprise analytics platform without giving up on safety, reliability, or auditability. This repo contains the code referenced in the article — the long snippets that were lifted out to keep the narrative readable. (The plain-English glossary lives next to the article, one level up.)

---

## Contents

```
.
├── README.md                 # You are here
├── guardrails/
│   ├── sql_validator.py      # sqlglot AST SQL safety checker (§1)
│   └── pipeline_stages.py    # Alias-contract validator + Stage Pipeline (§4)
├── reliability/
│   └── fallback_chain.py     # Model cooldown, session stickiness, last-resort override (§5)
├── telemetry/
│   └── postgres_schema.sql   # `fw_genai_logs` telemetry schema (§5)
├── governance/
│   └── agent_cache.py        # BYOK-safe per-request agent cache (§6)
└── demo/                     # runnable, no keys/DB/network — see demo/README.md
    ├── demo_sql_validator.py
    └── demo_fallback_chain.py
```

## Running the demos

```bash
pip install sqlglot sqlparse
python demo/demo_sql_validator.py     # §1
python demo/demo_fallback_chain.py    # §5
```

See [`demo/README.md`](demo/README.md) for what each one shows.

## How to use this repo

- **Reading the article first?** Each section in the article links to the file here that shows the underlying code in full.
- **Browsing this repo first?** Open the [article][article] for the architectural context — each file here is a fragment of a larger system and only makes sense alongside the patterns it implements.
- **The code is illustrative, not a drop-in library.** It's extracted from production code in ForeWarn-BI-Agent and lightly cleaned for publication. Deterministic logic is implemented in full and exercised by `demo/`; the only pieces left as thin adapters are true external boundaries — the LLM/agent construction in `agent_cache.py` (a lazy LangChain/LangGraph adapter) and table-alias resolution in `sql_validator.py` (noted inline). Full integration with the Orchestrator is project-specific.

## Section → file map

| Article section | Pattern | File |
|---|---|---|
| §1 The Contract Layer Is the Reliability Layer | Structural SQL validation (sqlglot AST) | [`guardrails/sql_validator.py`](guardrails/sql_validator.py) |
| §4 Deterministic Layers Create Reliability | Stage Pipeline + alias-contract validator | [`guardrails/pipeline_stages.py`](guardrails/pipeline_stages.py) |
| §5 Reliability Is an Operational Problem | Fallback Chain (cooldowns + stickiness) | [`reliability/fallback_chain.py`](reliability/fallback_chain.py) |
| §5 Reliability Is an Operational Problem | Structured telemetry schema | [`telemetry/postgres_schema.sql`](telemetry/postgres_schema.sql) |
| §6 Governance, Ownership, and Sovereignty | BYOK agent-cache discipline | [`governance/agent_cache.py`](governance/agent_cache.py) |

## Patterns kept inline in the article

The deterministic Router (§3), Orchestrator-owned context plumbing (§4), and portable user state (§6) have short snippets that are part of the argument itself — those stay inline in the article rather than getting lifted out here.

## License

*Add your preferred license here when publishing.*
