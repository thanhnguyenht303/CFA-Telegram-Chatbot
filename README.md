# CFA Level I Telegram Vocabulary Bot

Production-ready MVP for a Telegram chatbot that helps CFA Level I candidates learn vocabulary and exam-stem phrases using a weekly study timeline, scheduled delivery, quizzes, weak-word tracking, and spaced repetition.

The implementation follows the attached product spec as the source of truth. When the spec left choices open, this MVP chooses the simplest robust path: Python, `python-telegram-bot`, SQLAlchemy, SQLite, APScheduler, FastAPI health/admin endpoints, seed vocabulary, and optional LLM hooks that are disabled by default.

## Features

- Telegram commands: `/start`, `/today`, `/review`, `/quiz`, `/progress`, `/weak`, `/topic`, `/nextweek`, `/pause`, `/resume`, `/settings`, `/export`, `/research`, `/export_my_data`, `/delete_my_data`, `/error`.
- `/research <topic> <number>` uses OpenAI web research to propose new CFA Level I terms, then adds only user-approved terms to the learning database.
- Scheduled messages with per-user timezone support:
  - Monday-Friday 07:30: 5 new vocab/phrases.
  - Monday-Friday 21:40: 3 mini-review prompts.
  - Saturday 09:00: weekly quiz.
  - Sunday 18:30: weekly recap and weak words.
- Timeline import from CSV or JSON. Google Sheets can be supported by exporting the sheet to CSV for MVP.
- Seed vocabulary works without any LLM integration.
- Optional LLM interface is isolated in `services/llm.py`; failure or absence of an LLM never blocks scheduled content.
- OpenAI research is isolated in `services/research.py`; without `OPENAI_API_KEY`, the bot returns a clear setup message.
- SQLite local database with SQLAlchemy models that remain PostgreSQL-friendly.
- Duplicate prevention using normalized terms and aliases such as `YTM`, `yield-to-maturity`, and `yield to maturity`.
- Content QA gate: scheduler selects only `qa_status in ('approved', 'auto_approved')`.
- Custom quiz flow with A/B/C inline buttons so every answer updates quiz attempts, review state, and weak terms.
- Privacy commands for data export and deletion.
- FastAPI `/health`, `/ready`, and protected admin progress endpoint.
- Docker and Docker Compose support.

## Project Structure

```text
src/cfa_vocab_bot/
  admin_api.py              FastAPI app
  bot.py                    Telegram application factory
  config.py                 Pydantic environment config
  db.py                     SQLAlchemy engine/session setup
  jobs.py                   Scheduled send jobs
  models.py                 Database schema
  scheduler.py              APScheduler job registration
  services/                 Import, selection, quiz, export, privacy, spaced repetition
  telegram/                 Handlers, formatters, inline keyboards
data/
  seed_vocab.json           MVP approved vocab pool
  sample_timeline.csv       Importable study plan
  sample_timeline.json      Importable study plan
tests/                      Core logic tests
scripts/                    Convenience CLI wrappers
```

## Database Schema

The schema includes the MVP and expanded tables from the spec:

- `users`
- `user_settings`
- `study_plan`
- `vocab_items`
- `vocab_aliases`
- `vocab_sources`
- `delivery_log`
- `review_state`
- `quiz_results`
- `quiz_questions`
- `quiz_attempts`
- `content_generation_log`
- `research_suggestions`
- `scheduler_jobs`
- `system_events`

`vocab_items` includes QA and curriculum fields such as `qa_status`, `confidence_score`, `curriculum_year`, `los_ids`, `official_topic_weight`, `last_verified_at`, and `status`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```text
TELEGRAM_BOT_TOKEN=your-token
DATABASE_URL=sqlite:///./data/cfa_vocab.db
DEFAULT_TIMEZONE=America/Chicago
```

Initialize and seed the database:

```powershell
.\.venv\Scripts\python.exe -m cfa_vocab_bot init-db
.\.venv\Scripts\python.exe -m cfa_vocab_bot seed data/seed_vocab.json
```

Import the sample global timeline:

```powershell
.\.venv\Scripts\python.exe -m cfa_vocab_bot import-timeline data/sample_timeline.csv
```

Run the bot:

```powershell
.\.venv\Scripts\python.exe -m cfa_vocab_bot bot
```

Run the FastAPI admin/health app:

```powershell
.\.venv\Scripts\python.exe -m cfa_vocab_bot api --host 0.0.0.0 --port 8000
```

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot only | Telegram bot token. Never log or commit it. |
| `DATABASE_URL` | Yes | Defaults to `sqlite:///./data/cfa_vocab.db`. Use PostgreSQL in production if needed. |
| `OPENAI_API_KEY` | No | Enables `/research` and future optional LLM providers. Scheduled seed-vocab delivery still runs without it. |
| `OPENAI_RESEARCH_MODEL` | No | Model used for `/research`; defaults to `gpt-5.4-mini`. |
| `OPENAI_TIMEOUT_SECONDS` | No | Timeout for OpenAI research calls; defaults to `60`. |
| `WEBHOOK_SECRET` | Production webhook | Secret token for Telegram webhook validation. |
| `ADMIN_USER_IDS` | No | Comma-separated Telegram user IDs with admin rights. |
| `ADMIN_API_KEY` | Admin API | Token required by protected admin endpoints. |
| `DEFAULT_TIMEZONE` | No | Default user timezone. |
| `DEFAULT_DAILY_SEND_TIME` | No | Default `07:30`. |
| `DEFAULT_MINI_REVIEW_TIME` | No | Default `21:40`. |
| `DEFAULT_WEEKLY_QUIZ_TIME` | No | Default `09:00`. |
| `DEFAULT_WEEKLY_RECAP_TIME` | No | Default `18:30`. |
| `POLLING` | No | `true` for local polling, `false` for webhook. |
| `WEBHOOK_URL` | Webhook mode | HTTPS webhook URL. |

## Timeline Format

Required fields:

- `week_number`
- `start_date`
- `end_date`
- `main_topic`

Recommended fields:

- `subtopics`
- `learning_objectives`
- `curriculum_year`
- `exam_window`
- `exam_date`
- `official_topic_weight`
- `los_ids`
- `reading_or_module_name`
- `exam_phase`

CSV lists can be comma- or semicolon-separated. JSON can be a list or an object with a `study_plan` list.

## Telegram Usage

After `/start`, upload a CSV or JSON timeline in Telegram. The bot imports it for that user and maps the current date to the current CFA topic.

Examples:

```text
/settings timezone America/Chicago
/settings daily_send_time 07:30
/settings daily_vocab_count 5
/settings exam_date 2027-02-20
/research Fixed Income 10
/export csv
/export anki
/error duration convexity callable bond
```

Inline buttons update mastery and review state:

- `I know this`
- `Review later`
- `Give example`
- `Quiz me`
- `Too easy`
- `Too hard`

Callback data is intentionally short, for example `know:123`, `review:123`, and `quiz:8:4:B`.

## Research Workflow

`/research <topic> <number>` calls the OpenAI Responses API with web search enabled. The prompt asks the model to search public CFA Level I-relevant resources, prioritize useful terms for the requested topic, avoid verbatim paid/copyrighted explanations, and return structured candidates with source tracking.

Example:

```text
/research Fixed Income 10
```

The bot then:

1. Requests more than the requested count so duplicates can be filtered.
2. Removes terms already covered by `vocab_items` or aliases.
3. Saves remaining terms to `research_suggestions` with `status = suggested`.
4. Shows a compact suggestion list with Approve/Reject buttons.
5. Creates an active `vocab_items` row only when you approve a suggestion.

Approved research terms use `qa_status = approved`, are source-tracked in `vocab_sources`, and become eligible for daily delivery. They do not count as learned until they are delivered or reviewed.

## Spaced Repetition

The MVP uses the schedule from the spec:

| State | Next review |
| --- | --- |
| New | Next day |
| Correct 1 | 3 days |
| Correct 2 | 7 days |
| Correct 3 | 14 days |
| Correct 4 | 30 days |
| Wrong | Next day |
| Wrong multiple times | Weak list |

## Quiz Rules

Weekly quizzes are generated from terms delivered during the current study week. If fewer than 20 delivered terms exist, the bot fills from approved seed vocab for that topic. Questions use three choices, plausible distractors from nearby CFA terms, explanations, and per-question attempt logging.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Covered core logic:

- Duplicate detection and alias normalization.
- Spaced repetition intervals.
- Timeline import.
- Daily duplicate prevention.
- QA gate for `needs_review`.
- Quiz generation and grading.
- CSV and Anki export.
- Quiet-hours and exam-phase scheduling rules.

## Docker

Create `.env`, then:

```powershell
docker compose up --build cfa-vocab-bot
```

Run the optional API profile:

```powershell
docker compose --profile api up --build
```

SQLite is persisted through the `./data:/app/data` volume.

## Deployment Notes

- Local MVP: polling + SQLite is acceptable.
- Production: prefer PostgreSQL, HTTPS webhook, `WEBHOOK_SECRET`, and a process manager/container platform.
- Back up SQLite by copying the DB file while the bot is stopped, or use PostgreSQL dumps in production.
- Do not store copyrighted mock questions or paid explanations verbatim. Seed content is rewritten/original and source-tracked.
- Scheduler job failures are written to `scheduler_jobs`; application events can be added to `system_events`.
- `/research` uses the OpenAI Responses API with web search and structured outputs. If `OPENAI_API_KEY` is missing or the request fails, the bot reports the error and does not modify `vocab_items`.

## Implementation Decisions

- Google Sheet import is represented as CSV import for MVP because the spec allows CSV/JSON and the user request explicitly asks for CSV or JSON support.
- LLM integration is a clean interface, not a hard dependency, so delivery never fails because an API key is missing.
- Research suggestions are stored separately from active vocab because the user explicitly approves which words enter the learning pool.
- The admin API is intentionally small: health, readiness, and protected user progress.
- The weekly quiz uses a custom inline-button flow instead of Telegram native polls so the app can persist `response_time_seconds`, explanations, weak-term updates, and adaptive review state.
