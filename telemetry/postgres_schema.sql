-- =====================================================================
-- fw_genai_logs — structured telemetry for the GenAI agent layer.
--
-- Companion code for Pattern B.6 of "Designing for Determinism: GenAI
-- Inside a Mature BI-Analytics Platform". See the article for context.
--
-- Three tables: sessions, turns, tool_calls. The turn-level table below
-- is the workhorse referenced in the article. Companion `sessions` and
-- `tool_calls` tables follow the same shape — structured columns for the
-- things we'd query, JSONB for the things we wouldn't, FK back to
-- session_id / turn_id so a session can be reconstructed end-to-end.
--
-- Two intentional design choices worth flagging at the schema level:
--   1. Guardrail columns log every turn (action IN 'blocked', 'warned',
--      'modified', 'allowed') — logging only blocks gives a biased
--      dataset; logging actions across the board gives a true denominator.
--   2. The `feedback` column captures user up/down votes inline so we can
--      correlate quality with model_id, guardrail action, or duration in
--      a single SQL query.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS fw_genai_logs;

-- ---------------------------------------------------------------------
-- Turns: one row per user message / agent response cycle.
-- ---------------------------------------------------------------------
CREATE TABLE fw_genai_logs.fw_genai_logs_turns (
    syspk             BIGSERIAL  NOT NULL,
    session_id        TEXT       NOT NULL,
    turn_id           TEXT       NOT NULL,    -- t-1, t-2... per session
    turn_number       INTEGER    NOT NULL,

    created_at        TIMESTAMP  NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMP,
    duration_ms       INTEGER,

    model_id          TEXT       NOT NULL,
    user_message      TEXT       NOT NULL,
    uploaded_files_json   JSONB,
    enriched_message_json TEXT,

    -- Guardrails: what fired and what it did, even when it allowed the turn.
    guardrail_applied TEXT,
    guardrail_action  TEXT
                      CHECK(guardrail_action IS NULL OR guardrail_action IN
                           ('blocked', 'warned', 'modified', 'allowed')),
    guardrail_detail  TEXT,

    input_tokens      INTEGER    NOT NULL DEFAULT 0,
    output_tokens     INTEGER    NOT NULL DEFAULT 0,
    tool_call_count   INTEGER    NOT NULL DEFAULT 0,

    assistant_response_text TEXT,
    artifacts_json    JSONB,
    full_response_json JSONB,

    status            TEXT       NOT NULL DEFAULT 'success'
                      CHECK(status IN ('success', 'error', 'cancelled', 'guardrail_blocked')),
    error_message     TEXT,

    feedback          TEXT       CHECK(feedback IS NULL OR feedback IN ('up', 'down')),
    feedback_at       TIMESTAMP,

    CONSTRAINT pk_fgl_turns PRIMARY KEY (syspk),
    CONSTRAINT uq_fgl_turns_session_turn UNIQUE (session_id, turn_id),
    CONSTRAINT fk_fgl_turns_session FOREIGN KEY (session_id)
        REFERENCES fw_genai_logs.fw_genai_logs_sessions(session_id)
);

-- Indexes for the queries we actually run.
CREATE INDEX IF NOT EXISTS ix_fgl_turns_session_turn
    ON fw_genai_logs.fw_genai_logs_turns (session_id, turn_number);
CREATE INDEX IF NOT EXISTS ix_fgl_turns_model_status
    ON fw_genai_logs.fw_genai_logs_turns (model_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_fgl_turns_guardrail
    ON fw_genai_logs.fw_genai_logs_turns (guardrail_action, created_at)
    WHERE guardrail_action IS NOT NULL;

-- ---------------------------------------------------------------------
-- Sessions and tool_calls companion tables.
--
-- Sketched below — fill in to match the columns your Orchestrator emits.
-- The shape follows the same convention: structured columns for queryable
-- fields, JSONB for the open-ended ones, FK back to session_id.
-- ---------------------------------------------------------------------

-- CREATE TABLE fw_genai_logs.fw_genai_logs_sessions (
--     session_id     TEXT       NOT NULL PRIMARY KEY,
--     user_id        TEXT,
--     started_at     TIMESTAMP  NOT NULL DEFAULT NOW(),
--     last_seen_at   TIMESTAMP,
--     using_user_key BOOLEAN    NOT NULL DEFAULT FALSE,
--     metadata_json  JSONB
-- );

-- CREATE TABLE fw_genai_logs.fw_genai_logs_tool_calls (
--     syspk        BIGSERIAL NOT NULL PRIMARY KEY,
--     session_id   TEXT      NOT NULL,
--     turn_id      TEXT      NOT NULL,
--     tool_name    TEXT      NOT NULL,
--     started_at   TIMESTAMP NOT NULL DEFAULT NOW(),
--     duration_ms  INTEGER,
--     status       TEXT      NOT NULL,
--     input_json   JSONB,
--     output_json  JSONB,
--     error_message TEXT,
--     CONSTRAINT fk_fgl_tc_turn FOREIGN KEY (session_id, turn_id)
--         REFERENCES fw_genai_logs.fw_genai_logs_turns(session_id, turn_id)
-- );
