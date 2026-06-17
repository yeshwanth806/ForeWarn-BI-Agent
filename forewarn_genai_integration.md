# Integrating AI into a Live BI Platform — The Patterns That Actually Held Up

### Six production patterns from layering GenAI onto a production enterprise analytics platform.

*ForeWarn-BI-Agent, in production, ~12 MCP tools, three LLM providers, schema and reporting contracts the agent conforms to.*

*All code lives in [`fw_bi_agent_open_code/`](https://github.com/yeshwanth806/ForeWarn-BI-Agent/tree/main/fw_bi_agent_open_code). The section openers and highlighted lines carry the system-level argument. New to the jargon? There's a [plain-English glossary](https://github.com/yeshwanth806/ForeWarn-BI-Agent/blob/main/GLOSSARY.md).*

![Architecture overview — a single probabilistic LLM bounded by deterministic control layers: a regex Router, fault-isolated MCP subprocesses, structural Validators, a context/governance wrapper, and Postgres telemetry.](https://raw.githubusercontent.com/yeshwanth806/ForeWarn-BI-Agent/main/images/image1.png)

---

A user said they couldn't reproduce a turn they'd run an hour earlier. We pulled the logs to replay it. The session context on the tool calls was wrong. `session_id` had drifted mid-conversation — two turns that belonged to the same session were logged under different ones. On a separate call, the tool had picked up the wrong `model_id`. The turn had run on a different model than the user had selected.

Nothing crashed. The response had looked fine. The audit trail was silently broken.

The fix was not a better prompt. The fix was taking those fields out of the model's hands — a deterministic wrapper at the request boundary now owns them on every tool call. That single incident is the whole argument of this post, in miniature.

> **The agent isn't reliable because the model is reliable. It's reliable because it sits behind a system that already was.**

![Results card — four before/after metrics from the production integration, each tagged to the section that explains it.](https://raw.githubusercontent.com/yeshwanth806/ForeWarn-BI-Agent/main/images/image4.png)

*Operational numbers are SQL queries over our production telemetry; correctness rates were evaluated against versioned golden sets. How we measure: §5.*

---

**TL;DR.** ForeWarn is a 15-year-old enterprise analytics platform. We layered a conversational AI onto it — chat, NL-to-SQL, dashboard generation, ETL configuration, data profiling, etc. The patterns that moved it from "demo" to "production" had almost nothing to do with the prompt. They were about what we *kept the model out of*. The platform's existing contracts — alias schemas, chart definitions, governed SQL access — are not constraints to work around. They are the substrate. The wager underneath all six patterns: for enterprise GenAI, the differentiator won't be access to models — it'll be folding them into mature systems without weakening reliability, traceability, or governance. Two rules drive everything below:

> **Use probabilistic systems for interpretation. Use deterministic systems for control.**
>
> **If a thing is already deterministic, keep it that way. If it can't be, let the LLM draft, then validate or transform the output into something deterministic before you act on it.**

---

## §1. The Contract Layer Is the Reliability Layer

The naive safety check for LLM-generated SQL is a regex that rejects anything containing `DROP`, `DELETE`, `INSERT`. That check is structurally wrong — SQL has nested structure that regex cannot reason about. The reason it is wrong, and what we replaced it with, is the entire argument of this section.

> **The worst failure mode for an LLM agent is not being wrong. It is being wrong with confidence.**

Confidently-wrong SQL runs. Confidently-wrong SQL returns numbers. A user who trusts the agent might act on those numbers before anyone notices the column was hallucinated.

```python
# WRONG — surface check; misses nested structure
if re.search(r"\b(DROP|DELETE|INSERT)\b", sql, re.I):
    reject()
```

We replaced the regex with a real parse tree. Our first attempt reached for `sqlparse`, but `sqlparse` only *tokenizes* — it hands back a flat token stream, so telling the `FROM` inside `EXTRACT(YEAR FROM col)` apart from a real table clause still meant hand-rolling stateful walk logic that was easy to get wrong. We moved to `sqlglot`, which builds an actual Abstract Syntax Tree (AST): every construct becomes a typed node, so validation is node-type checks instead of token bookkeeping. The validator confirms exactly one top-level statement, ensures it's a read (`SELECT` or `WITH`), rejects forbidden operations anywhere in the tree, and checks every referenced table and column against the allowed schema.

```python
# RIGHT — parse to a real AST with sqlglot, then check typed nodes.
#   EXTRACT(YEAR FROM t.created_at) becomes a function node, so the FROM
#   inside it never looks like a table clause — no token bookkeeping needed.
root = sqlglot.parse_one(sql, read=DIALECT)

if not isinstance(root, (exp.Select, exp.Union, exp.With)):
    reject("only SELECT/WITH allowed")

for table in root.find_all(exp.Table):   # only real table references surface
    check_against_schema(table.name)
```

→ Full AST-based validator: [`fw_bi_agent_open_code/guardrails/sql_validator.py`](https://github.com/yeshwanth806/ForeWarn-BI-Agent/blob/main/fw_bi_agent_open_code/guardrails/sql_validator.py)

The headline: **structural validation, not surface filtering, is the table-stakes safety boundary for SQL-generating LLMs** — and it is only tractable to write because ForeWarn's schema and access layers already define the structure to validate against.

On governance-sensitive fields, deterministic code overrules the model outright: a regex PII pre-screen runs alongside the classifier, and when the two disagree, regex wins and the classification's confidence is downgraded. A false positive is cheaper than a leaked column.

*SQL incompatibility — "parses but fails against our schema or chart contract" — went from 36% to under 8%. Still not zero. We don't think it ever will be.*

**The enterprise platform is the control surface that makes GenAI capabilities safe to expose.** The model does not replace the platform; the platform makes the model safe.

---

## §2. Legacy Platforms Are the Substrate, Not the Constraint

A user once uploaded data where the only viable dimension column had ~500 distinct values — a borderline categorical, not a true low-cardinality dimension. The LLM happily projected it as `dimension_1` in a visualization. The validator from §1 passed; the alias contract was met. The platform then handled the 500-bar visualization gracefully, because it has had years to learn that real users do exactly this.

> **The validator catches contract violations. It doesn't catch poor judgment.**

ForeWarn's accumulated robustness — its tolerance for messy data, its handling of edge cases real users actually hit — caught what our validators couldn't. That isn't a backup. That is the foundation the validators sit on.

And that reframes the whole project. Most "how we built our AI agent" posts describe a fresh repo. Most enterprise GenAI work doesn't look like that. ForeWarn is an enterprise data-integration and analytics platform that businesses have depended on for operational and strategic analytics since the 2010s — production-grade, with established workflows, reporting structures, and downstream dependencies. It was never designed as a GenAI-first platform.

ForeWarn-BI-Agent is the chat-and-agent layer we built on top. The agent does not own the underlying contracts — viz config schema, chart definitions, SQL alias conventions, dashboard format. It has to *conform* to them. Violate a chart contract and dashboards that humans built by configuring those contracts break. Invent a column alias and exports break, because downstream consumers expect a fixed shape.

Many AI-first architectures assume mature enterprise systems slow innovation. In practice, the platform had already solved the problems GenAI systems eventually rediscover — access control, auditability, workflow sequencing, validation boundaries, telemetry, governed data access — and the AI layer inherited them instead of rebuilding them. The Stage Pipeline of §4 only works because the alias contracts already existed to validate against. The Fallback Chain of §5 only matters because there was already a request flow to wrap. The BYOK pattern of §6 is portable because the platform already separated identity and data ownership cleanly.

Throughout the project it was tempting to describe the platform's contracts as constraints the AI layer had to work around. Looking back, that framing was exactly wrong. **Mature enterprise platforms are not legacy baggage. They are the substrate that makes probabilistic intelligence safe to deploy.**

---

## §3. LLMs Operate Inside Boundaries

We had two dashboard generators — v1 returns config plus rendered HTML for on-screen display, v2 returns just config JSON for downstream consumers. Both are needed. Their docstrings looked nearly identical because their jobs were nearly identical, and the LLM picked one by something close to chance — often v2, silently returning JSON when the user expected to see something on screen.

Better docstrings did not fix that. **Making v2 invisible by default did.** The Router only includes v2 when the user message matches a specific phrase pattern (`"config file"`, `"raw config"`, `"no html"`, that family). Otherwise v2 is not in the LLM's toolbox at all.

Hiding isn't enough. When the user explicitly asks for v2, we also remove v1 from that turn's toolbox. The model never sees two near-identical tools side by side, so it never hedges with a clarifying question.

That was the harder version of a problem we'd already partly solved. Our first implementation registered all ~12 MCP tools on every request and let the LLM pick. Two things broke. First, ~2,000 tokens of tool schema rode along with every user message. Second, when two tools' descriptions overlapped at all, the LLM coin-flipped between them, and prompt engineering didn't reliably fix it.

What stuck was a deterministic **Router**. A regex pass over the user message detects intent — file summary, data profiling, SQL, dashboard, viz config — unions the matching tool groups, and falls back to the full set when nothing matches. The LLM still chooses *within* the filtered group, but among 3–4 tools instead of 12.

The Router reads session state, not just the message. A cached preview or an uploaded file keeps the relevant tool group bound, so a bare "go ahead" on the next turn still routes correctly. Stateless regex alone breaks multi-turn flows.

*Honest note: we planned a tiny-LLM disambiguation fallback for ambiguous messages and deliberately didn't ship it — unioning all tool groups is always safe, and it skips an LLM call on every ambiguous turn.*

![Tool-routing flow — a regex intent router narrows ~12 tools to the matched groups before the LLM sees them; the old "bind all 12 tools" path is deprecated.](https://raw.githubusercontent.com/yeshwanth806/ForeWarn-BI-Agent/main/images/image2.png)

> **Disambiguate with cheap deterministic code before you ask the LLM.**

It saves tokens, removes a class of hallucination, and gives you something you can unit-test.

*Per-turn input tokens dropped from ~3,500 to under 1,500 — roughly a 60% reduction in tool-schema overhead alone, before counting savings from cleaner LLM choices.*

Data access follows the same rule: the model never gets unrestricted database visibility — every interaction passes through interfaces where ForeWarn already enforces query constraints, schema boundaries, audit logging, and access policy.

Over time the architecture became progressively less *agentic* and more orchestrated. The LLM handles ambiguity. Enterprise systems retain ownership of correctness, validation, and control.

**The model can request actions; infrastructure retains authority over execution.**

---

## §4. Deterministic Layers Create Reliability

Hallucinated column names. Missing mandatory aliases. SQL referencing tables not in the source. That's the failure profile of dashboard generation when one prompt is doing everything — layout, chart-type pick, column classification, SQL rewrite — at once. It almost worked. The failures were the kind retries don't fix.

> **When the LLM fails, fall back to rules — not to more LLM.**

What stuck was a **Stage Pipeline** — three stages, each with a narrower contract:

1. **Intent** — layout + chart types
2. **Classify** — each column to dimension or metric
3. **Rewrite** — SQL projected to the alias contract

After each stage, a deterministic validator runs. Pass → continue. Fail → retry once. Fail again → stop and fall back to deterministic rules ("unknown columns are dropped, unknown metrics aggregate as `SUM`") to produce a valid config that way. Two wrong answers from the same prompt is a signal to start afresh, not to keep spinning the wheel.

The alias contract is the kind of thing the validators check: each chart type requires SQL to project aliases matching `dim{n}_name` or `metric{n}` — one regex, checked deterministically, with the chart type's mandatory subset verified against the platform's chart registry.

![Three-stage pipeline — Intent, Classify, Rewrite, each gated by a deterministic validator; pass continues, one retry is allowed, and a second failure falls back to deterministic rules that still produce a valid (degraded) config.](https://raw.githubusercontent.com/yeshwanth806/ForeWarn-BI-Agent/main/images/image3.png)

→ Full validator and stage-orchestration: [`fw_bi_agent_open_code/guardrails/pipeline_stages.py`](https://github.com/yeshwanth806/ForeWarn-BI-Agent/blob/main/fw_bi_agent_open_code/guardrails/pipeline_stages.py)

When a single prompt is too big to validate, split it. Smaller contracts are easier to test and easier to fall back from. Retry loops on the same prompt rarely converge. A deterministic degraded-but-valid output beats another spin of the wheel.

The biggest payoff was not accuracy — it was the shift from AI-generated **code** to AI-generated **config**. For a 30-vizlet dashboard, end-to-end latency went from 50–55s to 15–20s, output tokens from ~1,100 to ~300 per generation. Once the config has been validated, a deterministic builder turns it into HTML in milliseconds. The LLM never touches HTML.

Our data-onboarding flow takes this to its limit: the model produces a semantic profile of the file; deterministic templates generate every SQL artifact — DDL, upserts, validation queries. **The LLM emits no SQL at all.**

*Honest cost: three LLM round-trips on the happy path instead of one — about 2–3 seconds of extra latency per generation, roughly 7–8%. We accepted it because the retry costs on failures used to be a meaningful fraction of all attempts. Reliability won.*

For irreversible writes we split compute from commit: the LLM runs once, its output is cached to disk, and the user confirms against that frozen result. Confirm never re-calls the model — what the user approved is exactly what gets written.

The session_id-drift incident was one similar pattern at a different layer. Context variables — `session_id`, `model_id`, `api_key` — are set at request entry, one place, not twelve. A wrapper inspects each tool's schema and fills or overwrites those fields on every call before it goes out. The LLM is never *trusted* with `session_id` — a model that forgets or mangles it cannot corrupt the audit trail, because the value never depends on the model repeating it correctly.

**If a field is deterministic given the request context, its correctness should never depend on the prompt.** If it does, eventually the model will get it wrong — and the failure will be silent, which is the worst kind.

---

## §5. Reliability Is an Operational Problem

Two weeks into running the system, someone asked: *"how often is LLM-API timing out for paying users?"* We couldn't answer. Logs were files. The schema was "whatever printf wrote that day." That gap — between failures happening and failures being visible — is the gap this section is about.

Once GenAI moves into production, reliability becomes a runtime systems problem rather than a prompting problem — many of our early failures came from infrastructure behavior under load, not from wrong model outputs.

### Fallback is a system concern, not a per-tool retry

Every early LLM outage produced the same ticket: *"the agent stopped working."* Each tool that called the LLM had its own retry logic, none of it consistent. A 503 in one tool didn't tell another tool anything useful, and users sometimes saw raw API errors.

We pulled fallback out of the tools and into the LLM-call layer that already wrapped every model invocation. One module — the **Fallback Chain** — owns the model chain and handles three things:

- **Cooldowns.** A failed model is skipped for the next ten minutes.
- **Session stickiness.** A user's session stays locked to its working model for the whole conversation.
- **Last-resort override.** When every model is cooling simultaneously, the override ignores cooldowns for that one turn so the user still gets an answer.

```python
# (excerpt — full pick_model_chain in repo)
chain: list[str] = []

def _add(mid: str) -> None:
    if mid and mid not in chain and mid not in cooling:
        chain.append(mid)

_add(effective_primary)            # session stickiness first
for mid in all_ids:
    if len(chain) >= MAX_MODEL_ATTEMPTS:
        break
    _add(mid)                      # then everything not cooling

if not chain:                      # everything cooling — override
    chain = [effective_primary] + [m for m in all_ids if m != effective_primary]
    chain = [m for m in chain if m]
```

→ Full `pick_model_chain`, cooldown bookkeeping, and stickiness helpers: [`fw_bi_agent_open_code/reliability/fallback_chain.py`](https://github.com/yeshwanth806/ForeWarn-BI-Agent/blob/main/fw_bi_agent_open_code/reliability/fallback_chain.py)

Push fallback down once and reliability becomes a property of every code path that calls an LLM — not a property of the ones you remembered to add it to.

*Provider-side 503s visible to users dropped from ~7% to under 1%. The providers didn't get more reliable — we stopped letting one bad model take the agent down with it.*

### Isolate faults, then make them queryable

**Fault isolation.** MCP tools run in a stdio subprocess spawned per request. There's a startup cost — tens of milliseconds, not seconds. What we get is fault isolation: a tool can crash, run out of memory, leave file handles open, leak global state, and none of it touches the Orchestrator or the next request. One incident shaped our timeout discipline: a tool call once hung mid-execution and never returned, holding resources, slowing every other request. Subprocess isolation alone doesn't save you from that. So in addition, an agent-level timeout kills the turn even when nothing has crashed. Two layers, because either one alone has a hole.

**Queryability.** We moved logging into Postgres — three tables (sessions, turns, tool calls), structured columns for what we'd query, JSONB for the rest. The guardrail columns log *every* turn, including the ones the guardrail allowed — logging only blocks gives you a biased dataset. All logging writes are wrapped in try/except inside the logger.

> **Trust is an auditable layer, not a promise.** For any turn ever run, the telemetry answers: who ran it and when, on which model, the exact enriched prompt the LLM received, the response the user saw, input and output tokens, whether guardrails passed, warned, or blocked — and for every tool call inside the turn, the arguments, the output, the sequence, and how long it took. The entire lifecycle of every interaction is queryable.
>
> It is also how we measure. The operational numbers in this post — latency, tokens, error rates — are SQL queries over this telemetry. The correctness numbers — like §1's SQL-incompatibility rate — were evaluated against versioned golden sets: curated inputs and expected outcomes for every tool, exact values where a tool is deterministic, structural assertions plus a scoring rubric where it isn't.

→ Full schema (sessions / turns / tool_calls) and the guardrail / feedback columns that earn the most queries: [`fw_bi_agent_open_code/telemetry/postgres_schema.sql`](https://github.com/yeshwanth806/ForeWarn-BI-Agent/blob/main/fw_bi_agent_open_code/telemetry/postgres_schema.sql)

Subprocesses keep failures from spreading; structured Postgres logs let us see them. Either one alone is a half-system.

**Timeouts, retry control, cooldowns, fallback routing, subprocess isolation, and execution tracing are first-class architectural concerns, not implementation details.**

---

## §6. Governance, Ownership, and Sovereignty

A user pastes their own API key into the session. From the next turn forward, every LLM call in their session runs through *their* key, on *their* provider account, against *their* quota and audit logs. We don't proxy it. We don't store it. The key lives in memory only for the duration of the session and is gone when the session ends.

That's the easy claim. Here's what it actually costs to honor.

Governance, in practice, is about answering five questions explicitly:

- **Who owns state?**
- **Who controls execution?**
- **Who mediates data exposure?**
- **Who retains auditability?**
- **Which parts of the system remain deterministic regardless of provider behavior?**

### BYOK and model neutrality, done honestly

The UI lists models from three providers — Gemini, OpenAI, Anthropic. Behind that single dropdown are two paths: the default path runs through a **ForeWarn-managed API key**; the BYOK path runs through the user's own key. The provider is detected from the model ID prefix, and the appropriate LangChain `ChatModel` is loaded at call time. Switching paths requires no code change on our side — just a different value in one request field.

The detail that matters:

> **When a session is using a user-supplied key, the agent we build for that session is rebuilt fresh for every request, never cached, never reused for any other user.**

The cache key includes a `using_user_key` boolean; only ForeWarn-managed-key agents are cached, because holding a user-key agent forever would mix that user's key into an agent another user could hit. The per-request rebuild cost is on purpose.

```python
# (excerpt — full agent cache in repo)
# Per-request agent cache keyed by (model_id, frozenset(group_names), using_user_key).
cache_key = (model_id, groups, using_user_key)
cached = _agent_cache.get(cache_key)
if cached is not None:
    return cached
...
# Only cache the ForeWarn-managed-key variants; user-key agents are
# per-session by design — holding them forever would mix a user's key
# into an agent another user could hit.
if not using_user_key:
    _agent_cache[cache_key] = agent
```

→ Full per-request agent cache with the `using_user_key` cache-key discipline: [`fw_bi_agent_open_code/governance/agent_cache.py`](https://github.com/yeshwanth806/ForeWarn-BI-Agent/blob/main/fw_bi_agent_open_code/governance/agent_cache.py)

BYOK error handling falls out of the same architectural choice. When a user's key is bad, the very first call fails loudly: the Orchestrator classifies the auth failure, tells the user immediately, and stops the turn — before fallback logic can mask it as a silent provider switch. That explicit, early error is only possible because the Orchestrator owns the key, not the LLM.

> *For CTOs: BYOK is a sovereignty story for your customers — their key, their account, their audit trail. For engineers: it's a cache-key discipline. The `using_user_key` boolean in one dict key is the difference between a performance optimization and a cross-tenant security incident.*

### State the user owns is portable; state inside a tool is not

Our NL-to-SQL feature supports versioning — generate, modify, revert, list. The obvious design keeps version history inside the tool. We did the opposite. The tool is stateless. The Orchestrator owns version history, snapshots it to disk per session, and could hand the file back to the user verbatim. The tool gets `prior_versions` injected into every call; it returns a `versions_state` field; the Orchestrator captures and persists.

There's a broader idea here. **The LLM is most useful at the *cold start* — turning a blank page into a credible first draft.** After that, the human owns it: modify, revert, compare. The LLM is the cheap, fast first author; the user is the editor with veto power.

The confirmation step is where uncertainty surfaces: duplicate rows, cast failures, PII columns, and low-confidence classifications are shown before the user approves. Model doubt becomes a human decision instead of a silent guess.

Session memory lives in two places — fast in-memory state for the happy path, JSON snapshots on disk for restart durability. Users can also drop individual turns from the conversation context — manual memory hygiene that complements BYOK.

Portability is what makes state defensible in an enterprise conversation: the customer can export it, audit it, and walk away with it. Conversational memory is not durable enterprise state. Workflow state, credentials, version history, and audit trails are platform-owned. The provider is replaceable; the data is yours. **State on disk under the user's session ID is portable; state inside a long-running tool process is not.**

---

## §7. What Generalized — and Where the Boundary Belongs

Three groups of lessons. The patterns; not the numbers — your tool count, latencies, and contract shapes will all be different.

**What we moved out of the prompt:**

- Tool selection (deterministic Router on intent regex, not LLM picking from 12).
- Session context — `session_id`, `model_id`, `api_key` — set at request entry, auto-filled by a wrapper. The model is never trusted with plumbing.
- Retry and fallback logic (pulled up to the LLM-call layer, owned by one module, not scattered across tools).

**What we moved into infrastructure:**

- Structural validators (a sqlglot AST walk and contract checks, not regex surface filters).
- Subprocess isolation per request + agent-level timeouts. Either alone has a hole.
- Postgres telemetry with denominators — log every turn the guardrail touched, not just the ones it blocked.
- BYOK as a cache-key discipline. The `using_user_key` boolean is the whole story.

**What we learned about legacy:**

- The platform's existing contracts are what validators validate against. You don't have to invent a spec.
- The platform's accumulated robustness catches what validators can't (the 500-distinct-values story).
- Mature platforms accelerate GenAI integration; they don't slow it down.

The pattern underneath all three: routing, disambiguation, fallback, validation, plumbing, state — each started as a job we expected the prompt to handle, and each ended up living somewhere deterministic. Somewhere we could test, log, and reason about without rolling the dice on a model.

> **Use probabilistic systems for interpretation. Use deterministic systems for control.**

One scope note: this boundary is right for regulated, audited enterprise data, where a confident-wrong number has downstream cost. A low-stakes creative assistant should push the boundary the other way. But in our world the lesson repeated throughout the project: prompts became thinner, orchestration became stronger, validators became stricter — and the system became *more* useful, not less. The long-term differentiator for enterprise GenAI will not be access to models. It will be integrating them into mature environments without weakening reliability, traceability, or governance. Most enterprise GenAI work is **bounding a probabilistic component inside a platform that already works** — and the teams that ship are the ones who figure out where the deterministic boundary belongs, and put the LLM on the right side of it.

---

*All code, the [glossary](https://github.com/yeshwanth806/ForeWarn-BI-Agent/blob/main/GLOSSARY.md), and the long snippets lifted out of this article are in [`fw_bi_agent_open_code/`](https://github.com/yeshwanth806/ForeWarn-BI-Agent/tree/main/fw_bi_agent_open_code).*

---

*Honest note: The architecture, the scars, and the production incidents are ours — earned the long way, in the system this article describes. The LLM helped with the wording; it didn't invent the substance.*

---

*Written by **Yeshwanth Dendi**, architect of ForeWarn-BI-Agent at Compegence. The scars in this post are first-hand.*
