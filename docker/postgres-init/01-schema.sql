CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS episodic_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(64) NOT NULL,
    turn_index INTEGER NOT NULL,
    valid_time TIMESTAMPTZ NOT NULL,
    recorded_time TIMESTAMPTZ DEFAULT NOW(),
    event_type VARCHAR(32) NOT NULL,
    target_entity VARCHAR(255),
    payload JSONB NOT NULL,
    outcome_status VARCHAR(16) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    consolidated BOOLEAN DEFAULT FALSE,
    consolidated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_episodic_session_time ON episodic_events(session_id, valid_time DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_hash ON episodic_events(content_hash);
CREATE INDEX IF NOT EXISTS idx_episodic_payload_gin ON episodic_events USING GIN (payload);
CREATE INDEX IF NOT EXISTS idx_episodic_unconsolidated ON episodic_events(valid_time ASC) WHERE NOT consolidated;

CREATE OR REPLACE FUNCTION notify_episodic_event()
RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('new_episode_channel', NEW.event_id::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_episodic_event_notify ON episodic_events;
CREATE TRIGGER trg_episodic_event_notify
AFTER INSERT ON episodic_events
FOR EACH ROW EXECUTE FUNCTION notify_episodic_event();
