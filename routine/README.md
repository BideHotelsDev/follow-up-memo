# The Claude Code routine

With `EXTRACTION_MODE=routine` the app doesn't call the Claude API. Each Claude request (read a meeting's notes,
write a follow-up email) waits in a queue, and a scheduled Claude Code routine on Bide's Claude plan answers it
through the app's service API. The app then checks each answer exactly as it checks an API answer (quotes must be in
the notes, dates and emails must be backed up) and carries on: drafts, Slack messages, David's summary.

The routine runs in Anthropic's cloud, so the app must be deployed (Railway) at a public HTTPS address first.

## Trade-offs

- **Slower.** Routines run at most once an hour, so drafts arrive within about an hour of the notes, plus up to one
  poll interval. (The PRD's target with the API is 30 minutes.)
- **Shares the plan's usage limits.** If the plan is out of usage, requests wait; nothing is lost. Today flags
  meetings Claude hasn't answered for over 3 hours, and Admin → Connections shows the queue.
- **Tied to the account that owns the routine.** If that seat goes, extraction stops (and Today says so).
- Check that running a business automation on the plan fits Bide's Claude terms.

## Set up

1. Generate a token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. On Railway, set on both services: `EXTRACTION_MODE=routine` and `SERVICE_API_TOKEN=<the token>`.
3. In Claude Code, create a routine (`/schedule`, or https://claude.ai/code/routines):
   - Schedule: hourly in working hours, e.g. `5 7-19 * * 1-5` (UTC; 08:05–20:05 UK summer time, weekdays).
   - No repository needed. Tools: Bash, Read, Write.
   - Environment variables `FOLLOWUP_URL` (the app's address, no trailing slash) and `FOLLOWUP_TOKEN` (the token),
     set in the routine's environment settings, not in the prompt. If the environment limits outbound network
     access, allow the app's domain.
   - Prompt: the contents of `routine/prompt.md`.
4. Run the routine once by hand and check Admin → Connections: "Last answer" should update and the queue empty.

## Switching back to the API

Set `EXTRACTION_MODE=api` and `ANTHROPIC_API_KEY`. Requests still waiting in the queue are asked again through the
API on the next run, and the routine can be paused.
