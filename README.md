# Determinism Patterns for GenAI in Enterprise Analytics

Companion code for the article **["Designing for Determinism: GenAI Inside a Mature BI-Analytics Platform"][article]**.

The article describes eight patterns we used to embed a conversational AI layer (ForeWarn-BI-Agent) on top of a governed enterprise analytics platform without giving up on safety, reliability, or auditability. This repo contains the code snippets referenced in the article — the long ones that were lifted out to keep the narrative readable, plus a glossary for anyone who wants a plain-English definition of the terms.

[article]: ../architecture-blog-v13.md

---

## Contents

```
.
├── README.md                 # You are here
├── GLOSSARY.md               # Plain-English definitions for terms used in the article
├── guardrails/
│   ├── sql_validator.py      # AST-walking SQL safety checker (Pattern A.3)
│   └── pipeline_stages.py    # V1 alias-contract validator for the Stage Pipeline (Pattern A.2)
├── reliability/
│   └── fallback_chain.py     # Model cooldown, session stickiness, last-resort override (Pattern B.5)
└── telemetry/
    └── postgres_schema.sql   # `fw_genai_logs` turn-level schema (Pattern B.6)
```

## How to use this repo

- **Reading the article first?** Each pattern in the article links to the file here that shows the underlying code in full.
- **Browsing this repo first?** Open the [article][article] for the architectural context — each file here is a fragment of a larger system and only makes sense alongside the patterns it implements.
- **The code is illustrative, not a drop-in library.** It's extracted from production code in ForeWarn-BI-Agent and lightly cleaned for publication. Module-level state, imports, and helper functions are shown as they appear in the article; full integration with the Orchestrator is project-specific.

## Pattern → file map

| Pattern | Article section | File |
|---|---|---|
| Stage Pipeline + alias-contract validator | A.2 | [`guardrails/pipeline_stages.py`](guardrails/pipeline_stages.py) |
| Structural SQL validation (AST walk) | A.3 | [`guardrails/sql_validator.py`](guardrails/sql_validator.py) |
| Fallback Chain (cooldowns + stickiness) | B.5 | [`reliability/fallback_chain.py`](reliability/fallback_chain.py) |
| Structured telemetry schema | B.6 | [`telemetry/postgres_schema.sql`](telemetry/postgres_schema.sql) |

## Patterns kept inline in the article

A.1 (deterministic Router), A.4 (Orchestrator-owned context plumbing), C.7 (BYOK cache discipline), and C.8 (portable user state) have short snippets that are part of the argument itself — those stay inline in the article rather than getting lifted out here.

## License

*Add your preferred license here when publishing.*
