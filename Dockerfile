# python:3.13-slim chosen over full Debian (~900MB) or Alpine (~50MB).
# Slim (~130MB) avoids the C-extension compatibility issues Alpine can
# cause, while staying lean enough for production use.
# FROM python:3.13 - resulting in image size  0f 420mb

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY app.py github_client.py ./


RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser


EXPOSE 8080

# HEALTHCHECK tells Docker (and orchestrators like Kubernetes) how to
# verify the container is alive and serving traffic.
#
# --interval=30s     check every 30 seconds
# --timeout=5s       if no response within 5s, count as failed
# --start-period=5s  give gunicorn 5s to boot before checks begin
# --retries=3        3 consecutive failures → container marked "unhealthy"
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:app"]