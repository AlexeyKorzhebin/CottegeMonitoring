# Preserve production 0.3.5 (unpublished patch); replace only audited dispatcher/parser.
ARG BASE_IMAGE=cottage-monitoring:status-topics-base-270d3e5dac6a
FROM ${BASE_IMAGE}
COPY src/cottage_monitoring/mqtt/topic_parser.py /usr/local/lib/python3.12/site-packages/cottage_monitoring/mqtt/topic_parser.py
COPY src/cottage_monitoring/services/ingestor.py /usr/local/lib/python3.12/site-packages/cottage_monitoring/services/ingestor.py
