from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cfa_vocab_bot.models import StudyPlan
from cfa_vocab_bot.schemas import TimelineRow

REQUIRED_TIMELINE_FIELDS = {"week_number", "start_date", "end_date", "main_topic"}


def _parse_date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value).strip())


def _parse_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if text.startswith("["):
        loaded = json.loads(text)
        return [str(item).strip() for item in loaded if str(item).strip()]
    return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace("%", "").strip())


def _row_from_mapping(raw: dict[str, Any]) -> TimelineRow:
    normalized = {key.strip(): value for key, value in raw.items()}
    missing = REQUIRED_TIMELINE_FIELDS - normalized.keys()
    if missing:
        raise ValueError(f"Timeline row is missing required fields: {', '.join(sorted(missing))}")
    return TimelineRow(
        week_number=int(normalized["week_number"]),
        start_date=_parse_date(normalized["start_date"]),  # type: ignore[arg-type]
        end_date=_parse_date(normalized["end_date"]),  # type: ignore[arg-type]
        main_topic=str(normalized["main_topic"]).strip(),
        subtopics=_parse_list(normalized.get("subtopics")),
        learning_objectives=_parse_list(normalized.get("learning_objectives")),
        curriculum_year=int(normalized["curriculum_year"])
        if normalized.get("curriculum_year")
        else None,
        exam_window=normalized.get("exam_window") or None,
        exam_date=_parse_date(normalized.get("exam_date")),
        official_topic_weight=_parse_float(normalized.get("official_topic_weight")),
        los_ids=_parse_list(normalized.get("los_ids")),
        reading_or_module_name=normalized.get("reading_or_module_name") or None,
        exam_phase=normalized.get("exam_phase") or "learning",
    )


def read_timeline(path: str | Path) -> list[TimelineRow]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return [_row_from_mapping(row) for row in csv.DictReader(file)]
    if path.suffix.lower() == ".json":
        loaded = json.loads(path.read_text(encoding="utf-8"))
        rows = loaded.get("study_plan", loaded) if isinstance(loaded, dict) else loaded
        if not isinstance(rows, list):
            raise ValueError("JSON timeline must be a list or an object with a study_plan list.")
        return [_row_from_mapping(row) for row in rows]
    raise ValueError("Timeline import supports CSV and JSON files.")


def import_timeline(
    session: Session,
    *,
    user_id: int | None,
    path: str | Path,
    replace_existing: bool = True,
    source: str = "upload",
) -> tuple[int, list[str]]:
    rows = read_timeline(path)
    warnings: list[str] = []
    if replace_existing:
        session.execute(delete(StudyPlan).where(StudyPlan.user_id == user_id))
    for row in rows:
        if row.curriculum_year is None:
            warnings.append(f"Week {row.week_number}: curriculum_year missing; MVP will still run.")
        if row.exam_date is None:
            warnings.append(f"Week {row.week_number}: exam_date missing; exam phase is less adaptive.")
        session.add(
            StudyPlan(
                user_id=user_id,
                week_number=row.week_number,
                start_date=row.start_date,
                end_date=row.end_date,
                main_topic=row.main_topic,
                subtopics=row.subtopics,
                learning_objectives=row.learning_objectives,
                curriculum_year=row.curriculum_year,
                exam_window=row.exam_window,
                exam_date=row.exam_date,
                official_topic_weight=row.official_topic_weight,
                los_ids=row.los_ids,
                reading_or_module_name=row.reading_or_module_name,
                exam_phase=row.exam_phase,
                source=source,
            )
        )
    session.flush()
    return len(rows), warnings


def plan_for_date(session: Session, user_id: int | None, today: dt.date) -> StudyPlan | None:
    user_plan = session.scalar(
        select(StudyPlan)
        .where(
            StudyPlan.user_id == user_id,
            StudyPlan.start_date <= today,
            StudyPlan.end_date >= today,
        )
        .order_by(StudyPlan.start_date.desc())
    )
    if user_plan:
        return user_plan
    return session.scalar(
        select(StudyPlan)
        .where(
            StudyPlan.user_id.is_(None),
            StudyPlan.start_date <= today,
            StudyPlan.end_date >= today,
        )
        .order_by(StudyPlan.start_date.desc())
    )


def next_plan_after(session: Session, user_id: int | None, today: dt.date) -> StudyPlan | None:
    user_plan = session.scalar(
        select(StudyPlan)
        .where(StudyPlan.user_id == user_id, StudyPlan.start_date > today)
        .order_by(StudyPlan.start_date.asc())
    )
    if user_plan:
        return user_plan
    return session.scalar(
        select(StudyPlan)
        .where(StudyPlan.user_id.is_(None), StudyPlan.start_date > today)
        .order_by(StudyPlan.start_date.asc())
    )

