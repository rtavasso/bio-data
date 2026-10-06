# Colloquy pilot image: the web app (built here) and the commons API in one container.
#   docker build -f deploy/Dockerfile -t colloquy:pilot .
#   docker run -p 8765:8765 -v /srv/commons:/commons colloquy:pilot
# The commons directory is a volume (created with `bio community init` or `bio commons demo`).
# Serving accounts mode records multi-tenant tenancy: live dispatch then requires <commons>/sandbox.toml.

FROM node:22-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Agent checkouts are staged from this source tree (agent_setup.copy_research_tools needs the
# checkout layout: AGENTS.md, src/, contracts/, examples/, docs/ and .agents/skills/).
COPY pyproject.toml uv.lock README.md AGENTS.md ./
COPY src ./src
COPY contracts ./contracts
COPY examples ./examples
COPY docs ./docs
COPY .agents ./.agents
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/* \
 && uv sync --frozen --no-dev --extra commons
COPY --from=web /src/web/dist /app/web/dist
ENV PATH=/app/.venv/bin:$PATH COLLOQUY_WEB_DIST=/app/web/dist PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 colloquy && mkdir /commons && chown colloquy /commons
USER colloquy
VOLUME /commons
EXPOSE 8765
ENTRYPOINT ["bio", "commons", "--root", "/commons", "serve", "--host", "0.0.0.0", "--mode", "accounts"]
