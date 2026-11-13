-- Provision these NOINHERIT roles and database CONNECT separately, without secrets here.
GRANT USAGE ON SCHEMA platform_metrics TO platform_metrics_writer, platform_metrics_reader, platform_metrics_maintenance;
GRANT INSERT ON platform_metrics.batches, platform_metrics.samples TO platform_metrics_writer;
GRANT SELECT (producer, batch_id, body_sha256) ON platform_metrics.batches TO platform_metrics_writer;
GRANT SELECT ON platform_metrics.batches, platform_metrics.samples TO platform_metrics_reader;
GRANT SELECT (producer, batch_id, received_at), DELETE ON platform_metrics.batches TO platform_metrics_maintenance;
