FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install cloudflared
RUN curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

# Install Claude Code CLI
RUN curl -fsSL https://cli.claude.ai/install.sh | sh || true
# If the install script doesn't work in Docker, users mount their own claude binary
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

# Shared workspace for inter-agent communication
RUN mkdir -p /app/shared

EXPOSE 8765

# Start everything
CMD ["bash", "start.sh"]
