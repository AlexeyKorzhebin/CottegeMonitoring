# Build context: server/. The build script verifies and tags the approved local image.
FROM platform-metrics-base:approved-cc3c918041ea
COPY --chmod=0644 src/cottage_monitoring/config.py /usr/local/lib/python3.12/site-packages/cottage_monitoring/config.py
COPY --chmod=0644 src/cottage_monitoring/api/platform_metrics.py /usr/local/lib/python3.12/site-packages/cottage_monitoring/api/platform_metrics.py
COPY --chmod=0644 src/cottage_monitoring/platform_metrics_app.py /usr/local/lib/python3.12/site-packages/cottage_monitoring/platform_metrics_app.py
WORKDIR /
USER 65532:65532
ENTRYPOINT ["uvicorn"]
CMD ["cottage_monitoring.platform_metrics_app:app", "--host", "127.0.0.1", "--port", "8330", "--workers", "1", "--no-access-log"]
