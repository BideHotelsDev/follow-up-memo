# Bide Meeting Follow-up

Turns David's Gemini meeting notes into follow-ups that wait for approval: Gmail drafts to external attendees, Slack
DMs and channel digests for the team, a task list, and questions for David. The only automatic sends are the run
summary and weekly digest DMs to David, and (once Admin switches them on) due-date reminders to the team. Spec: "Meeting Follow-up System — PRD & System Design" (Claude Doc).

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

Checks: `pnpm check` (lint, format, types), `pnpm test:api`, `pnpm build:web`, and the browser tests
(`pnpm --filter @bide-followup/web e2e`, with the mock services and `E2E_BASE_URL` pointing at the app; desktop and
390 px phone widths, with an axe accessibility check). After changing an API model, run
`pnpm gen:types` and commit the result; CI fails if the types are out of date.

### With the mock services

`apps/api/mocks` stands in for Google (Drive, Calendar, OAuth, Gmail), Slack and Claude, serving two made-up
meetings, so the whole pipeline runs with no accounts or API key. What would have gone to Gmail and Slack is at
http://localhost:8400/inbox.

```sh
pnpm seed:mock        # a separate SQLite database, with a pretend Google connection
pnpm dev:mocks        # http://localhost:8400
pnpm dev:api:mock     # the API wired to the mocks (.env.mock)
pnpm dev:web
```

Sign in as `kyle@bidehotels.com` and run the pipeline with `POST /api/admin/runs` (or `pnpm dev:worker:mock` to run
it on the schedule).

## The web app

The pages follow the approved demo ("Meeting Follow-up Demo" artifact): **Today** (what waits for David, today's calls,
questions answered in place, next tasks), **Meetings** (what Gemini recorded and where each point went; reprocess),
**Email drafts** (preview, edit, open in Gmail, discard), **Slack drafts** (approve and post, approve all, edit,
discard), **Tasks** (by due date; a drawer to change owner, date and status), **How it works** and **Admin**
(connections, people, channels, skip rules, email tone and schedule, run log). A hotel filter and a "Viewing as"
switch sit in the header. On a phone the pages are a tab bar at the bottom (Today, Emails, Slack, Tasks,
More), a meeting or email opens in a sheet over its list, and Slack drafts keep Approve all in reach. Members (Russell, Sam) see only Today and their own tasks. Every approve, edit, discard,
answer and task change is recorded in `audit_log`.

## What Bide edits in Admin

Nothing about Bide itself is fixed in the code: the **properties** and **systems** (Admin → Properties; they feed the
property filter, the tags, the channel map and the extraction schema and prompt), the **people** and who is the
**Owner** (whose name appears in labels, prompts and Slack messages), the channel map, skip rules, email tone and
signature, and the **Impact targets** and time windows (Admin → Email and schedule; they start at the PRD's success
measures).

## Impact

The Impact page (David and Admin) measures, from the app's own records and from launch onwards: meetings followed up
within 24 hours (by week), time from meeting end to drafts and to David acting, actions done on time, late, open
and overdue, open actions by owner, drafts approved without edits, tasks David had to give a different owner, his
days of use, and a time-saved estimate, each by hotel. It opens with what the app did (meetings read, actions captured, emails drafted, Slack messages sent,
questions settled, hours saved) and ends with how the app is performing: runs completed, meetings read without a
problem, time to drafts, drafts sent as written, tasks given to the right person, Claude usage, and meetings handled
by week. The PRD's success measures are shown against their targets.
There is no data from before launch; Admin can enter a before-launch rate and time (Admin → Email and schedule) to
show the comparison. Definitions are on the page. `pnpm seed:mock` adds eight weeks of made-up history so the page
has something to show locally.

## Pipeline

Every 10 minutes the worker (`bide_followup.worker`) runs `pipeline/run.py`:

1. **Discover**: Gemini notes in David's Drive changed in the last 3 days, not seen before and not changed in the last
   15 minutes, become queued meetings. Title skip rules apply here.
2. **Fetch**: the note as plain text and its Calendar event (by Gemini's attachment, else by title and time) for
   attendees. Attendee skip rules apply here.
3. **Extract**: one Claude call with the prompt in `prompts/extract_v3.md`, the Bide context from Admin settings and
   the schema in `schemas/extraction.py`. Problems (invalid JSON, quotes not in the notes, impossible dates, emails
   from nowhere) get one retry with the problems listed.
4. **Ground** (`pipeline/validate.py`): ungrounded actions are dropped, unsupported dates and emails cleared, and
   unowned or undated items become questions for David (5 at most).

5. **Generate** (`pipeline/outputs.py`): a Gmail draft to the external attendees, written by Claude from the
   validated summary (never the notes) in David's tone and signature (`prompts/email_v2.md`); a Slack DM draft per
   internal owner; a channel digest draft for the meeting's category or property. Sensitive meetings get no DMs or digest,
   and the email is flagged "review carefully". Outputs are upserted by (meeting, type, recipient), so a rerun updates
   drafts rather than duplicating them, and anything David has approved or discarded is left alone.
6. **Summarise** (`pipeline/summary.py`): one Slack DM to David listing the meetings processed. With failure alerts
   to `ADMIN_ALERT_SLACK_CHANNEL` (after two failed runs in a row), the only message posted without approval.

Separately, the worker checks every 10 minutes for scheduled messages (`pipeline/notices.py`): a weekday reminder to
each person with tasks due that day or overdue (off by default), and the owner's weekly digest. Each is recorded in
`notices` once per person per day or week, so a repeated check sends nothing new and a failed post is retried.

A meeting that fails is retried on the next run and marked failed after 3 attempts; a failed output (a Gmail draft,
the summary) is retried the same way and the meeting shows as partial meanwhile. Without Google connected the run
pauses; without `ANTHROPIC_API_KEY` meetings wait in the queue. Stored note text is deleted after 30 days.

## Claude: API or the Claude Code routine

`EXTRACTION_MODE=api` (the default) calls the Claude API with `ANTHROPIC_API_KEY`. `EXTRACTION_MODE=routine` runs on
Bide's Claude plan instead: each Claude request waits in a queue (`llm_jobs`), a scheduled Claude Code routine
answers it through the token-protected service API (`/api/service/v1`), and the pipeline carries on exactly as with
an API answer, checks included. Routines run at most hourly, so drafts arrive within about an hour. Setup, prompt and
trade-offs: `routine/README.md` and `apps/api/bide_followup/prompts/routine.md`. Admin → Connections shows the mode and the queue; Today flags
meetings Claude hasn't answered for over 3 hours.

## Dictation: Wispr Flow

Without setup, Wispr Flow works as David's dictation app: it types into any box, and ⌘/Ctrl Enter saves. With
`WISPR_API_KEY` (Wispr's voice API, by invitation from enterprise@wisprflow.ai) every editable box also gets a
**Dictate** button. The app makes a 15-minute client token (`POST /api/dictation/token`; the org key stays on the
server), the browser streams the microphone to Wispr's WebSocket as 16 kHz PCM, and Wispr's tidied text goes in at the
cursor. Names from Admin are sent as its dictionary. Wispr bills per use. The mocks serve a fake Wispr for dev and e2e.

## Golden set

`pnpm eval` runs extraction on the cases in `apps/api/eval/cases` and scores actions found, owners, due dates and
invented actions (see `apps/api/eval/run.py`). It calls the real Claude API and prints the cost. Real notes stay out
of git: only the made-up `example-*` cases are committed.

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
