-- One bounded transaction per invocation; scheduler and failure monitoring are separate.
BEGIN;
SET LOCAL statement_timeout = '5s';
WITH expired AS (
 SELECT producer, batch_id FROM platform_metrics.batches
 WHERE received_at < now() - interval '30 days'
 ORDER BY received_at LIMIT 1000
)
DELETE FROM platform_metrics.batches b USING expired e
WHERE b.producer = e.producer AND b.batch_id = e.batch_id;
COMMIT;
