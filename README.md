# CFA Level I Telegram Vocabulary Bot

Production-ready MVP for a Telegram chatbot that helps CFA Level I candidates learn vocabulary and exam-stem phrases using a weekly study timeline, scheduled delivery, quizzes, weak-word tracking, and spaced repetition.

The implementation follows the attached product spec as the source of truth. When the spec left choices open, this MVP chooses the simplest robust path: Python, `python-telegram-bot`, SQLAlchemy, SQLite, APScheduler, FastAPI health/admin endpoints, seed vocabulary, and optional LLM hooks that are disabled by default.

## Features

- Telegram commands: `/start`, `/today`, `/review`, `/quiz`, `/progress`, `/weak`, `/topic`, `/topics-display`, `/topics_display`, `/learning-setting`, `/learning_setting`, `/subtopic-add`, `/subtopic_add`, `/subtopic-list`, `/subtopic_list`, `/subtopic-clear`, `/subtopic_clear`, `/reset`, `/skip`, `/nextweek`, `/pause`, `/resume`, `/settings`, `/export`, `/research`, `/export_my_data`, `/delete_my_data`, `/error`.
- `/research <topic> <number>` uses OpenAI web research to propose new CFA Level I terms, then adds only user-approved terms to the learning database.
- Scheduled messages with per-user timezone support:
  - Monday-Friday 07:30: 5 new vocab/phrases.
  - Monday-Friday 21:40: 3 mini-review prompts.
  - Saturday 09:00: weekly quiz.
  - Sunday 18:30: weekly recap and weak words.
  - Daily plan-extension reminder when the current study-plan row has 2 days or fewer left and no next week is planned.
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
- `topic_learning_settings`
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

Optionally test the timeline importer from the CLI:

```powershell
.\.venv\Scripts\python.exe -m cfa_vocab_bot import-timeline data/sample_timeline.csv
```

Telegram users normally create a personal plan by uploading a CSV/JSON timeline in chat or by using `/learning-setting <topic> <weeks>`.

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

After `/start`, upload a CSV or JSON timeline in Telegram or build a plan with `/learning-setting <topic> <weeks>`. The bot stores the plan for that user and maps the current date to the current CFA topic.

Examples:

```text
/settings timezone America/Chicago
/settings daily_send_time 07:30
/settings daily_vocab_count 5
/settings exam_date 2027-02-20
/topics-display
/learning-setting Quantitative Methods 2
/subtopic-add Time Value of Money
/subtopic-list
/learning-setting Fixed Income 3
/skip
/reset
/research Fixed Income 10
/research Quantitative Methods - Hypothesis Testing 10
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

`/topics-display` shows all active approved vocab topics already available in the pool, with word counts. Telegram's official command menu only supports letters, numbers, and underscores, so `/topics_display` is registered in the menu and `/topics-display` is supported as a typed alias.

`/learning-setting <topic> <weeks>` appends that topic directly to your personal `study_plan`, for example `/learning-setting Quantitative Methods 2` followed by `/learning-setting Financial Statement Analysis 3` creates two Quant weeks and then three Financial Statement Analysis weeks. If your plan is empty, the first row starts on the Monday of your current local week; otherwise it starts after the last planned week. With no arguments, it displays your current `study_plan`. Telegram's command menu registers `/learning_setting`, and `/learning-setting` is supported as a typed alias.

The topic is validated against the approved vocab pool shown by `/topics-display`. Exact matches are stored with the canonical topic name. If the topic looks misspelled, the bot suggests the closest topic and does not write to `study_plan` until you rerun `/learning-setting` with the corrected topic.

`/subtopic-add <subtopic>` adds a focus area to the current active study-plan week, for example `/subtopic-add Time Value of Money`. `/subtopic-list` displays the current week's sub-topics. `/subtopic-clear` removes them from the current week. Telegram's command menu registers `/subtopic_add`, `/subtopic_list`, and `/subtopic_clear`; the hyphen commands are supported as typed aliases.

Daily vocab selection now uses sub-topics as a priority layer: terms matching the current week's sub-topics are delivered first, then the bot fills from the main topic, then from the broader approved pool if needed.

`/reset` clears your personal `study_plan` so you can build a fresh sequence. It also clears the saved topic pacing rows used by `/learning-setting`, because the MVP treats those rows as derived setup data for the plan.

`/skip` keeps the current study week in place, removes the remaining future weeks for the current topic, and shifts the next planned topic forward. Example: if you are in week 1 of a two-week Quantitative Methods block followed by Financial Statement Analysis, `/skip` removes the second Quant week so Financial Statement Analysis becomes next week.

When your current plan has 2 days or fewer left and there is no planned next week, the scheduler sends a reminder to extend the plan with `/learning-setting <topic> <weeks>`.

## Research Workflow

`/research <topic> <number>` calls the OpenAI Responses API with web search enabled. The prompt asks the model to search public CFA Level I-relevant resources, prioritize useful terms for the requested topic, avoid verbatim paid/copyrighted explanations, and return structured candidates with source tracking.

Example:

```text
/research Fixed Income 10
/research Quantitative Methods - Hypothesis Testing 10
```

The bot then:

1. Builds an exclusion list from existing terms and aliases for the requested topic.
2. Asks OpenAI to avoid those existing terms before generating candidates.
3. Requests extra candidates and retries when duplicate filtering leaves fewer than the requested count.
4. Removes terms already covered by `vocab_items`, aliases, or pending suggestions.
5. Saves remaining terms to `research_suggestions` with `status = suggested`, keeping the main topic and optional sub-topic separated.
6. Shows a compact suggestion list with Approve/Reject buttons.
7. Creates an active `vocab_items` row only when you approve a suggestion.

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
- User-built study-plan appending, reset, skip, and extension alerts.

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
- `/learning-setting` writes concrete weekly rows instead of storing only preferences, because that makes future delivery deterministic and visible through `/topic`, `/nextweek`, and the scheduler.
- The admin API is intentionally small: health, readiness, and protected user progress.
- The weekly quiz uses a custom inline-button flow instead of Telegram native polls so the app can persist `response_time_seconds`, explanations, weak-term updates, and adaptive review state.
