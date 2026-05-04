"""LLM-based job filtering using Gemini.

Two-stage filter driven by criteria.yaml:
  1. filter_by_industry()   — reject non-SW/IT roles (status: new → rejected)
  2. filter_by_experience() — reject jobs requiring >3 yrs (status: new → rejected | ready)
"""

import json
import logging
import os
import time
from pathlib import Path

import yaml
from google import genai

from db import Job, SessionLocal

log = logging.getLogger(__name__)

BATCH_SIZE = 10
BATCH_SLEEP = 5  # seconds between batches; keeps us under 15 RPM Gemini free tier

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _load_criteria() -> dict:
    path = Path(__file__).parent / "criteria.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _call_gemini(prompt: str) -> list[dict]:
    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0.1},
    )
    return json.loads(response.text)


def _build_industry_prompt(jobs: list, criteria: dict) -> str:
    ic = criteria["industry_filter"]
    accept = ", ".join(ic["accept_categories"])
    reject = ", ".join(ic["reject_categories"])
    ambiguous = ic["ambiguous_instruction"]

    jobs_json = json.dumps(
        [
            {
                "id": job.id,
                "title": job.title or "",
                "company_industry": job.company_industry or "",
                "description_preview": (job.description or "")[:300].replace("\n", " "),
            }
            for job in jobs
        ],
        ensure_ascii=False,
    )

    return f"""You are a job classification assistant.

ACCEPT categories (software/IT roles): {accept}
REJECT categories (non-software roles): {reject}
Ambiguous rule: {ambiguous}

For each job below, decide ACCEPT or REJECT based on whether it is a software/IT role.

Jobs: {jobs_json}

Respond ONLY with a JSON array, one object per job:
[{{"id": <int>, "decision": "ACCEPT" or "REJECT", "reason": "<one sentence>"}}]"""


def _build_experience_prompt(jobs: list, criteria: dict) -> str:
    ec = criteria["experience_filter"]
    max_years = ec["max_years"]
    reject_signals = "; ".join(ec["reject_signals"])
    accept_signals = "; ".join(ec["accept_signals"])

    jobs_json = json.dumps(
        [
            {
                "id": job.id,
                "title": job.title or "",
                "description_preview": (job.description or "")[:500].replace("\n", " "),
            }
            for job in jobs
        ],
        ensure_ascii=False,
    )

    return f"""You are a job experience-level classifier.

Rule: REJECT only if the posting EXPLICITLY requires MORE than {max_years} years of professional experience.
REJECT signals: {reject_signals}
ACCEPT signals: {accept_signals}
When in doubt, ACCEPT.

Jobs: {jobs_json}

Respond ONLY with a JSON array, one object per job:
[{{"id": <int>, "decision": "ACCEPT" or "REJECT", "reason": "<one sentence>"}}]"""


def filter_by_industry() -> tuple[int, int]:
    """Classify status='new' jobs as SW/IT or not.

    Rejected jobs → status='rejected'; survivors remain status='new'.
    Returns (accepted_count, rejected_count).
    """
    criteria = _load_criteria()
    session = SessionLocal()
    accepted = rejected = 0

    try:
        jobs = session.query(Job).filter(Job.status == "new").all()
        if not jobs:
            log.info("filter_by_industry: no new jobs to process")
            return 0, 0

        log.info("filter_by_industry: %d jobs, batch size %d", len(jobs), BATCH_SIZE)

        for i, batch in enumerate(_batches(jobs, BATCH_SIZE)):
            if i > 0:
                time.sleep(BATCH_SLEEP)

            try:
                decisions = _call_gemini(_build_industry_prompt(batch, criteria))
            except Exception as e:
                log.error("Gemini call failed for industry batch %d: %s", i, e)
                accepted += len(batch)  # fail-open: keep all
                continue

            id_map = {d["id"]: d["decision"] for d in decisions}
            for job in batch:
                if id_map.get(job.id, "ACCEPT") == "REJECT":
                    log.info("  REJECT (industry) #%d: %s @ %s", job.id, job.title, job.company)
                    job.status = "rejected"
                    rejected += 1
                else:
                    accepted += 1

            session.commit()

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    log.info("filter_by_industry done: %d accepted, %d rejected", accepted, rejected)
    return accepted, rejected


def filter_by_experience() -> tuple[int, int]:
    """Check experience requirements for surviving status='new' jobs.

    Approved → status='ready'; rejected → status='rejected'.
    Returns (ready_count, rejected_count).
    """
    criteria = _load_criteria()
    session = SessionLocal()
    ready = rejected = 0

    try:
        jobs = session.query(Job).filter(Job.status == "new").all()
        if not jobs:
            log.info("filter_by_experience: no new jobs remaining")
            return 0, 0

        log.info("filter_by_experience: %d jobs, batch size %d", len(jobs), BATCH_SIZE)

        for i, batch in enumerate(_batches(jobs, BATCH_SIZE)):
            if i > 0:
                time.sleep(BATCH_SLEEP)

            try:
                decisions = _call_gemini(_build_experience_prompt(batch, criteria))
            except Exception as e:
                log.error("Gemini call failed for experience batch %d: %s", i, e)
                for job in batch:
                    job.status = "ready"
                    ready += 1
                session.commit()
                continue

            id_map = {d["id"]: d["decision"] for d in decisions}
            for job in batch:
                if id_map.get(job.id, "ACCEPT") == "REJECT":
                    log.info("  REJECT (experience) #%d: %s @ %s", job.id, job.title, job.company)
                    job.status = "rejected"
                    rejected += 1
                else:
                    job.status = "ready"
                    ready += 1

            session.commit()

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    log.info("filter_by_experience done: %d ready, %d rejected", ready, rejected)
    return ready, rejected
