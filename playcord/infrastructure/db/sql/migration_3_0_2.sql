-- Migration 3.0.2
-- Canonicalize replay event storage in replay_events and backfill legacy rows.

CREATE TABLE IF NOT EXISTS replay_events
(
    event_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id         BIGINT           NOT NULL,
    sequence_number  INTEGER          NOT NULL,
    event_type       VARCHAR(100)     NOT NULL,
    actor_user_id    BIGINT,
    payload          JSONB            NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_replay_match_sequence UNIQUE (match_id, sequence_number),
    CONSTRAINT fk_replay_events_match FOREIGN KEY (match_id)
        REFERENCES matches (match_id) ON DELETE CASCADE,
    CONSTRAINT fk_replay_events_actor FOREIGN KEY (actor_user_id)
        REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT chk_replay_sequence CHECK (sequence_number >= 1)
);

CREATE INDEX IF NOT EXISTS idx_replay_events_match_seq
    ON replay_events (match_id, sequence_number);

CREATE INDEX IF NOT EXISTS idx_replay_events_actor_time
    ON replay_events (actor_user_id, created_at DESC)
    WHERE actor_user_id IS NOT NULL;

-- Backfill only matches that do not yet have canonical replay rows.
WITH legacy_match_ids AS (
    SELECT mm.match_id
    FROM match_moves mm
    WHERE mm.kind = 'system'
    GROUP BY mm.match_id
    HAVING NOT EXISTS (
        SELECT 1
        FROM replay_events re
        WHERE re.match_id = mm.match_id
    )
),
ranked_legacy AS (
    SELECT
        mm.match_id,
        ROW_NUMBER() OVER (
            PARTITION BY mm.match_id
            ORDER BY mm.move_number, mm.created_at, mm.move_id
        )::INTEGER AS sequence_number,
        COALESCE(mm.move_data ->> 'event_type', 'event') AS event_type,
        mm.user_id AS actor_user_id,
        (COALESCE(mm.move_data, '{}'::jsonb) - 'event_type') AS payload,
        COALESCE(mm.created_at, NOW()) AS created_at
    FROM match_moves mm
    JOIN legacy_match_ids lm ON lm.match_id = mm.match_id
    WHERE mm.kind = 'system'
)
INSERT INTO replay_events (
    match_id,
    sequence_number,
    event_type,
    actor_user_id,
    payload,
    created_at
)
SELECT
    match_id,
    sequence_number,
    event_type,
    actor_user_id,
    payload,
    created_at
FROM ranked_legacy;
