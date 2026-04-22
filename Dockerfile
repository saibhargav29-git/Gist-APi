# python:3.13-slim chosen over full Debian (~900MB) or Alpine (~50MB).
# Slim (~130MB) avoids the C-extension compatibility issues Alpine can
# cause, while staying lean enough for production use.
FROM python:3.13-slim

WORKDIR /app

# Copy requirements first to exploit Docker's layer cache:
# pip install only reruns when requirements.txt changes, not on every
# code change — keeps rebuild times fast in a CI/CD pipeline.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py github_client.py ./

# Documents which port this container uses (does not publish it).
# Publishing happens at `docker run -p 8080:8080` time.
EXPOSE 8080

# Exec form (JSON array) ensures Python is PID 1 and receives OS signals
# (SIGTERM) directly — critical for graceful shutdown in orchestrators
# like Kubernetes. Shell form would make /bin/sh PID 1 instead.
CMD ["python", "app.py"]