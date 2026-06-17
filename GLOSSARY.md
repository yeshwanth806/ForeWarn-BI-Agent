# Glossary — Terms used in the architecture blog

A plain-English companion to **["Integrating AI into a Live BI Platform — The Patterns That Actually Held Up"](forewarn_genai_integration.md)**. If you bumped into a term in the post and weren't sure what it meant, look it up here. Definitions are intentionally short and informal — not textbook-precise.

---

## LLM (Large Language Model)
The AI model that reads text and writes text — Gemini, GPT, Claude, etc. In this system, the LLM is the "brain" that interprets a user's question and decides what to do. It's powerful but not deterministic: ask it the same thing twice and you may get two slightly different answers.

## BI (Business Intelligence) tool
Software that lets people explore data — upload a spreadsheet, build charts, create dashboards, share them. Our ForeWarn BI is one of these. The article is about adding a chat interface on top of an existing BI-analytics platform.

## Greenfield project
A project started from a blank slate, with no existing code, contracts, or constraints to work around. ForeWarn was the opposite: the platform already existed and dictated many of the rules — which is the whole premise of §2.

## MCP (Model Context Protocol) tools
A standard way for an LLM to call external tools (run a SQL query, fetch a file summary, build a chart). Each tool is a small program with a defined input/output. Think of MCP tools as the LLM's hands — it decides what to do, the tools actually do it.

## Tool schema
A machine-readable description of what a tool does, what inputs it expects, and what it returns. The LLM reads this schema to know which tool to pick and how to call it. Schemas cost tokens — every tool you expose adds to the prompt size.

## Tokens (input/output tokens)
The unit LLMs charge by. Roughly, one token is three-quarters of a word. Every word in the prompt, the tool schemas, and the response counts. Reducing tokens = lower cost and faster responses.

## Hallucination
When an LLM confidently invents something that isn't true — a column name that doesn't exist, a function that was never written, a fact it can't actually know. The dangerous kind isn't obvious garbage; it's plausible-looking output that quietly breaks downstream.

## Router (deterministic router)
A piece of plain code (no AI) that looks at a user message and decides which tools are relevant. "Deterministic" means same input → same output, every time. We use it to narrow the LLM's choices before the LLM even sees the request.

## Regex (regular expression)
A compact pattern-matching language for text — e.g. "find any word ending in `_name`." Fast, predictable, and great for simple matches. Bad at understanding nested structure (which is why we use a parser, not regex, for SQL safety checks).

## Docstring
The short description written above a function in code, explaining what it does. The LLM reads tool docstrings to decide which tool to call. If two docstrings sound alike, the LLM gets confused.

## Fallback Chain
An ordered list of models to try when a call fails: start on the session's working model, and if it errors, fall through to the next healthy one. In this system the chain is capped at two attempts per turn (primary + one fallback), and a failed model is skipped while it's cooling. The user only sees an error if every option in the chain fails.

## Cooldown
A short "time-out" period for a model that just failed. If Gemini just returned an error, we skip it for the next 10 minutes instead of retrying immediately. Saves time and avoids hammering a struggling provider.

## Session stickiness
Once a user's conversation lands on a working model, we keep them on that model for the rest of the session. Otherwise the model could silently swap mid-conversation as cooldowns expire, and answers would feel inconsistent.

## 503 error
A standard "service unavailable" error from a server. Usually means the LLM provider is overloaded or temporarily down. Common enough that handling it gracefully is essential.

## Validator
Code that checks whether the LLM's output meets the rules before we act on it. Did the SQL parse cleanly? Do the column aliases match the contract? Are required fields present? If validation fails, we either retry or fall back to deterministic rules.

## Stage Pipeline
Our three-stage prompt structure for viz-config generation — **Intent** (layout + chart types), **Classify** (column → dimension or metric), and **Rewrite** (SQL → contract). A deterministic Validator gate sits between each stage. If a stage fails, we retry once; if it fails again, we stop and fall back to deterministic rules rather than spinning the wheel on more LLM attempts.

## Alias / Alias contract (SQL)
An alias is the name a column gets in a SQL query result — `SELECT amount AS metric1` makes "metric1" the alias. Our platform requires specific alias names (`dim1_name`, `metric1`, etc.) to render charts. The "alias contract" is that strict naming rule.

## Dimension and Metric (BI terms)
Two ways to think about a column. A **dimension** is something you group by — country, product, month. A **metric** is something you measure — revenue, count, average. Charts pair dimensions (X-axis) with metrics (Y-axis).

## Cardinality
The number of distinct values in a column. "Country" has low cardinality (~200). "User ID" has high cardinality (millions). Charts work best with low-cardinality dimensions; a 500-distinct-value column is a borderline case.

## Subprocess (and subprocess isolation)
A separate, isolated program spawned by the main app to do one job. If it crashes, leaks memory, or hangs, the main app keeps running — the damage is contained. We spawn a fresh subprocess per request so one misbehaving tool can't take down the Orchestrator or the next request.

## BYOK (Bring Your Own Key)
A pattern where users supply their own API key (e.g. their own OpenAI key) instead of using ours. They pay their own usage, and we never store or cache anything tied to their key. Important for enterprise privacy and cost control.

## Orchestrator
The central piece of code that coordinates everything — receives the user request, calls the Router, builds the LLM agent, runs the tools, handles fallback, writes logs. Think of it as the conductor; the LLM and tools are the musicians.

## ReAct agent
An LLM "agent" pattern that alternates between **Reasoning** ("I should look up the file first") and **Acting** ("call the file_summary tool"). LangGraph's `create_react_agent` (in `langgraph.prebuilt`) builds this loop for you. It's how the LLM uses tools step by step instead of answering in one shot.

## LangChain / ChatModel
LangChain is a Python library for building LLM apps. A `ChatModel` is its abstraction over different LLM providers — same interface whether you're calling Gemini, OpenAI, or Claude. Lets us swap providers without rewriting the calling code.

## System prompt
The hidden instructions given to the LLM at the start of every conversation — "you are a BI assistant, here are the tools you can use, follow these rules." Users don't see it. It's the LLM's job description.

## NL-to-SQL (Natural Language to SQL)
A feature where the user types a question in English ("top 10 customers by revenue") and the LLM writes the SQL query for it. Useful but risky — bad SQL against a real database can be slow, wrong, or destructive.

## DDL (Data Definition Language)
The subset of SQL that defines structure rather than reading data — `CREATE TABLE`, `ALTER`, and so on. In the data-onboarding flow, deterministic templates generate the DDL from a profile of the file; the LLM never writes it.

## SQL parser (vs. regex)
A parser reads SQL the way a database does — building a tree of statements, clauses, functions, etc. A regex just scans text. Parsers can tell that the `FROM` inside `EXTRACT(YEAR FROM col)` isn't a table reference; regex can't.

## AST (Abstract Syntax Tree)
The tree a parser builds from source — each construct (a SELECT, a function call, a table reference) is a typed node. Walking the tree lets you reason about structure rather than guess from text: the `FROM` inside `EXTRACT(YEAR FROM col)` is plainly a function argument, not a table. §1's SQL safety check walks a sqlglot AST. (Note: `sqlparse` only *tokenizes* — it does not build a true AST; `sqlglot` does.)

## Subquery
A SELECT statement nested inside another SELECT — a query within a query, written as a parenthesized SQL fragment. A real SQL parser (like sqlglot) represents each subquery as its own node in the syntax tree, so the validator can descend into it and check the tables and columns it references.

## Guardrail
Code that checks user input or LLM output for unsafe content — prompt injection attempts, attempts to query forbidden columns, attempts to leak sensitive data. A safety layer between the LLM and the rest of the system.

## PII (Personally Identifiable Information)
Data that can identify a person — name, email, phone, government ID. The system runs a regex PII pre-screen alongside the LLM classifier; when the two disagree, the regex wins — a false positive is cheaper than leaking a sensitive column.

## Telemetry / Audit trail
Telemetry is the data we record about how the system runs — every turn, every tool call, every error. The audit trail is being able to reconstruct *exactly* what happened in a past conversation. Without it, "the agent did something weird" is unanswerable.

## Golden set
A curated set of inputs paired with their expected outputs, version-controlled and re-run to measure correctness. For deterministic tools we assert exact values; for fuzzy ones, structural checks plus a scoring rubric. The article's *correctness* numbers (like the SQL-incompatibility rate) are measured against golden sets — distinct from the *operational* numbers (latency, tokens, error rates) measured from telemetry.

## JSONB
A PostgreSQL data type that stores JSON in a queryable, indexable form. Lets us write a column like `artifacts_json` that holds arbitrary structured data, and still run SQL against fields inside it. The flexibility of JSON with the power of SQL.

## Stateful vs. Stateless (tool)
A **stateful** tool remembers things between calls (it has memory). A **stateless** tool forgets — every call is fresh, with all needed context passed in. Stateless tools are easier to scale, restart, and reason about. We made our versioning tool stateless on purpose.

## Snapshot (session snapshot)
A point-in-time copy of session data, written to disk. If the server restarts, we can reload the snapshot and the user's draft history isn't lost. Cheap insurance against the kind of incident that erases work-in-progress.

## Vizlet
Our internal name for a single visualization (one chart, one KPI tile, one table) inside a dashboard. A 30-vizlet dashboard has 30 of these arranged on a single page.

## Viz config
A JSON description of a visualization — what chart type, what data source, what columns, what styling. The platform reads viz config and renders the chart. The LLM writes config, never HTML — keeping rendering deterministic and safe.

## Agent loop
The repeated cycle inside a ReAct agent: think → call a tool → read the result → think again → call another tool → ... → produce the final answer. One user message can trigger several loops before the agent is done.

## Cache key
A unique identifier used to look up something stored in memory for fast reuse. In our case, the cache key for an agent includes the model, the tool group, and *whether the user supplied their own API key* — the last bit is what prevents a security mix-up between users.
