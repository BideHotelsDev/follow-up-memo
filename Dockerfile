# One image for both Railway services: SERVICE_ROLE=api (default) or SERVICE_ROLE=worker.

FROM node:24-slim AS web
WORKDIR /repo
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/shared-types/package.json packages/shared-types/
RUN pnpm install --frozen-lockfile
COPY apps/web apps/web
COPY packages/shared-types packages/shared-types
RUN pnpm --filter @bide-followup/web build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api ./
RUN uv sync --frozen --no-dev
COPY --from=web /repo/apps/web/dist /app/web-dist
ENV PATH="/app/.venv/bin:$PATH" WEB_DIST_DIR=/app/web-dist
CMD ["sh", "start.sh"]
