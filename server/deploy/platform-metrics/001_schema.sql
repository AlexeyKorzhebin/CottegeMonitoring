-- Run as a migration administrator after provisioning platform_metrics_owner.
BEGIN;
CREATE SCHEMA platform_metrics AUTHORIZATION platform_metrics_owner;
CREATE TABLE platform_metrics.batches (
 producer text NOT NULL CHECK (producer = 'ai-server'), batch_id uuid NOT NULL,
 body_sha256 bytea NOT NULL CHECK (octet_length(body_sha256) = 32),
 created_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (producer, batch_id)
);
CREATE TABLE platform_metrics.samples (
 producer text NOT NULL, batch_id uuid NOT NULL, service text NOT NULL,
 metric text NOT NULL, unit text NOT NULL, observed_at timestamptz NOT NULL,
 status text NOT NULL CHECK (status IN ('observed','estimated','unknown')),
 value double precision, PRIMARY KEY (producer,batch_id,service,metric),
 FOREIGN KEY (producer,batch_id) REFERENCES platform_metrics.batches ON DELETE CASCADE,
 CHECK ((status = 'unknown' AND value IS NULL) OR (status <> 'unknown' AND value IS NOT NULL))
);
CREATE INDEX platform_metrics_batches_received ON platform_metrics.batches(received_at);
CREATE INDEX platform_metrics_samples_series_time ON platform_metrics.samples(service,metric,observed_at DESC);
ALTER TABLE platform_metrics.batches OWNER TO platform_metrics_owner;
ALTER TABLE platform_metrics.samples OWNER TO platform_metrics_owner;
COMMIT;
