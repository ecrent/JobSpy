"""
End-to-end JobSpy automation pipeline.

Stages:
  1. Scrape jobs → DB (status='new')
  2. LLM industry filter  (non-SW → status='rejected')
  3. LLM experience filter (>3yr req → status='rejected'; survivors → status='ready')
  4. Generate tailored CVs (status='ready' → 'cv_generated')
  5. Convert .docx → .pdf
  6. Send email with PDFs and job links
  7. Mark sent jobs as status='emailed'

Triggered by cron as user 'builder'. All output appended to logs/pipeline.log.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Configure logging before any local imports so basicConfig calls in sub-modules
# are no-ops and all loggers inherit handlers set here.
_PROJECT_DIR = Path(__file__).parent
_LOG_DIR = _PROJECT_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "pipeline.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s")
_file_handler = logging.FileHandler(_LOG_FILE)
_file_handler.setFormatter(_fmt)
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_fmt)
logging.root.setLevel(logging.INFO)
logging.root.addHandler(_file_handler)
logging.root.addHandler(_stream_handler)

# Load .env before local imports so os.getenv() calls at module level work.
from dotenv import load_dotenv
load_dotenv(_PROJECT_DIR / ".env")

from db import Job, SessionLocal
from email_sender import send_results_email
from generate_cvs import generate_cvs_for_ready_jobs, sanitize_filename
from llm_filter import filter_by_industry, filter_by_experience
from pdf_converter import convert_docx_to_pdf, PDF_OUTPUT_DIR

# Importing scrape_jobs_to_db triggers proxy validation at module level (~10-30s).
from scrape_jobs_to_db import scrape_and_store, SEARCH_TERMS, LOCATION

GENERATED_CVS_DIR = _PROJECT_DIR / "generated_cvs"

log = logging.getLogger("pipeline")


def _collect_cv_generated_jobs() -> tuple[list, list[str]]:
    """Return all status='cv_generated' jobs and their expected .docx paths."""
    session = SessionLocal()
    try:
        jobs = session.query(Job).filter(Job.status == "cv_generated").all()
        docx_paths = []
        for job in jobs:
            company = sanitize_filename(job.company or "unknown")
            title = sanitize_filename(job.title or "unknown")
            docx_paths.append(str(GENERATED_CVS_DIR / f"{company}_{title}_talasli_cv.docx"))
        session.expunge_all()
        return jobs, docx_paths
    finally:
        session.close()


def _mark_emailed(job_ids: list[int]) -> None:
    if not job_ids:
        return
    session = SessionLocal()
    try:
        session.query(Job).filter(Job.id.in_(job_ids)).update(
            {"status": "emailed"}, synchronize_session="fetch"
        )
        session.commit()
        log.info("Marked %d job(s) as 'emailed'", len(job_ids))
    except Exception as e:
        session.rollback()
        log.error("Failed to mark jobs as emailed: %s", e)
    finally:
        session.close()


def run_pipeline() -> None:
    start = datetime.now()
    log.info("=" * 60)
    log.info("Pipeline started at %s", start.isoformat())

    # --- Stage 1: Scrape ---
    log.info("Stage 1: Scraping jobs...")
    total_inserted = 0
    for term in SEARCH_TERMS:
        try:
            n = scrape_and_store(search_term=term, location=LOCATION, results_wanted=20)
            total_inserted += n
        except Exception as e:
            log.error("Scrape failed for term '%s': %s", term, e, exc_info=True)
    log.info("Stage 1 done: %d new job(s) inserted", total_inserted)

    # --- Stage 2: Industry filter ---
    log.info("Stage 2: Filtering by industry...")
    try:
        accepted, rejected = filter_by_industry()
        log.info("Stage 2 done: %d accepted, %d rejected", accepted, rejected)
    except Exception as e:
        log.error("Industry filter failed (continuing): %s", e, exc_info=True)

    # --- Stage 3: Experience filter ---
    log.info("Stage 3: Filtering by experience requirement...")
    try:
        ready, rejected = filter_by_experience()
        log.info("Stage 3 done: %d ready, %d rejected", ready, rejected)
    except Exception as e:
        log.error("Experience filter failed (continuing): %s", e, exc_info=True)

    # --- Stage 4: Generate CVs ---
    log.info("Stage 4: Generating tailored CVs...")
    try:
        generate_cvs_for_ready_jobs()
        log.info("Stage 4 done")
    except Exception as e:
        log.error("CV generation failed (continuing): %s", e, exc_info=True)

    # --- Stage 5: Collect jobs + convert to PDF ---
    log.info("Stage 5: Converting .docx → .pdf...")
    jobs, docx_paths = _collect_cv_generated_jobs()
    if not jobs:
        log.info("No cv_generated jobs found — nothing to email.")
        log.info("Pipeline finished in %.1fs", (datetime.now() - start).total_seconds())
        log.info("=" * 60)
        return

    pdf_paths = convert_docx_to_pdf(docx_paths, output_dir=str(_PROJECT_DIR / PDF_OUTPUT_DIR))
    log.info("Stage 5 done: %d/%d PDF(s) created", len(pdf_paths), len(docx_paths))

    # Match each PDF back to its job by filename stem.
    stem_to_job = {Path(d).stem: j for d, j in zip(docx_paths, jobs)}
    emailable_jobs = [stem_to_job[Path(p).stem] for p in pdf_paths if Path(p).stem in stem_to_job]

    # --- Stage 6: Send email ---
    log.info("Stage 6: Sending results email...")
    if pdf_paths:
        sent = send_results_email(jobs=emailable_jobs, pdf_paths=pdf_paths)
    else:
        log.warning("No PDFs to send — skipping email.")
        sent = False

    # --- Stage 7: Mark as emailed ---
    if sent:
        _mark_emailed([j.id for j in emailable_jobs])
        log.info("Stage 7 done")
    else:
        log.warning("Email not sent; jobs remain at status='cv_generated'")

    elapsed = (datetime.now() - start).total_seconds()
    log.info("Pipeline finished in %.1fs", elapsed)
    log.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
