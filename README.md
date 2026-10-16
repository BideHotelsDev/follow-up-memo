# Bide Meeting Follow-up

Turns David's Gemini meeting notes into follow-ups that wait for approval: Gmail drafts to external attendees, Slack
DMs and channel digests for the team, a task list, and questions for David. The only automatic send is the run
summary DM to David. Spec: "Meeting Follow-up System — PRD & System Design" (Claude Doc).

## Layout

- `apps/api`: FastAPI app, worker and pipeline (Python 3.12, uv, SQLAlchemy 2, Alembic). Package `bide_followup`.
- `apps/web`: React + Vite + TypeScript, Tailwind v4 and shadcn/ui, TanStack Query. Bide brand tokens in
  `src/index.css`.
- `packages/shared-types`: TypeScript types generated from the API's OpenAPI schema (`pnpm gen:types`).
- `slack/manifest.yaml`: the Slack app.

## Local development

```sh
cp .env.example .env              # then fill in TOKEN_ENCRYPTION_KEY at least
pnpm install
pnpm db:migrate && pnpm seed:demo # SQLite by default; docker compose up -d for Postgres on 5434
pnpm dev:api                      # http://localhost:8300
pnpm dev:web                      # http://localhost:5175 (proxies /api to the API)
```

With `AUTH_DEV_LOGIN=true` the sign-in page lets you sign in as any seeded person (e.g. `kyle@bidehotels.com`, Admin)
without Google.

Checks: `pnpm check` (lint, format, types), `pnpm test:api`, `pnpm build:web`. After changing an API model, run
`pnpm gen:types` and commit the result; CI fails if the types are out of date.

## Deploy (Railway)

One Docker image, two services, plus Railway Postgres:

- **api**: default role. Runs migrations and the seed on start, serves `/api` and the web app. Healthcheck
  `/api/health`, public domain.
- **worker**: `SERVICE_ROLE=worker`, no domain. Runs the scheduled pipeline.

Both need the variables in `.env.example`, with `DATABASE_URL` from the Postgres service.

## One-off setup

1. Google Cloud project with the OAuth consent screen set to **Internal** (no Google verification needed). Enable the
   Drive, Calendar and Gmail APIs. Add the two redirect URIs listed in `.env.example`.
2. Create the Slack app from `slack/manifest.yaml`.
3. Sign in as Admin, open **Connections**, connect David's Google account (David signs in on Google's screen) and
   install the Slack bot. Tokens are stored encrypted with `TOKEN_ENCRYPTION_KEY`.
4. Add people, their Slack member IDs and ownership areas under **People**.

## Guardrails

- No email is ever sent. `gmail.compose` would allow sending, so the code only ever creates, updates and deletes
  drafts, and a test enforces that.
- Slack messages are posted only when David approves them, apart from the run summary to David and failure alerts
  to Admin.
- OAuth tokens are encrypted at rest and never logged. Logs carry IDs, never note content.
