# Image for sandboxed agent checkouts (M3.6): the bio CLI at the same path as the pilot image
# (/app/.venv, so staged ./bin wrappers resolve) plus stock harness CLIs. No entrypoint: the
# runtime supplies the harness argv. Credentials are never baked in; they are mounted per run.
#   docker build -f deploy/agent.Dockerfile -t colloquy-agent:latest .
#   docker build -f deploy/agent.Dockerfile --build-arg HERMES_PACKAGE="hermes-agent==X" -t colloquy-agent:latest .
FROM python:3.12-slim
ARG CLAUDE_CODE_PACKAGE=@anthropic-ai/claude-code
ARG CODEX_PACKAGE=@openai/codex
ARG HERMES_PACKAGE=
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates nodejs npm \
 && rm -rf /var/lib/apt/lists/* \
 && if [ -n "$CLAUDE_CODE_PACKAGE" ]; then npm install -g "$CLAUDE_CODE_PACKAGE"; fi \
 && if [ -n "$CODEX_PACKAGE" ]; then npm install -g "$CODEX_PACKAGE"; fi \
 && if [ -n "$HERMES_PACKAGE" ]; then UV_TOOL_BIN_DIR=/usr/local/bin UV_TOOL_DIR=/opt/uv-tools uv tool install "$HERMES_PACKAGE"; fi
WORKDIR /app
COPY pyproject.toml uv.lock README.md AGENTS.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
