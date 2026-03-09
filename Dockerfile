FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux curl ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# Node.js (for npx MCP servers)
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# cloudflared
RUN ARCH=$(dpkg --print-architecture) && \
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}" \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code 2>/dev/null || true
ENV PATH="/root/.local/bin:$PATH"

# uv (for uvx MCP servers)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh generate-configs.sh

# Generate configs at build time (can be overridden by volume mounts)
RUN bash generate-configs.sh /app

RUN mkdir -p /app/shared

EXPOSE 8765

CMD ["bash", "start.sh"]
