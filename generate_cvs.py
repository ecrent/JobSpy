"""Main pipeline: read approved jobs → tailor CV per job → save .docx → update DB status.

Usage:
    python generate_cvs.py
"""

import logging
import os
import re
import time

from docx import Document

from cv_parser import find_sections, extract_section_text, MUTABLE_SECTIONS
from cv_tailor import tailor_cv
from cv_writer import write_tailored_cv
from db import SessionLocal, Job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
log = logging.getLogger(__name__)

BASE_CV_PATH = "talasli_cv_eng.docx"
OUTPUT_DIR = "generated_cvs"


def sanitize_filename(name: str) -> str:
    """Convert a string to a safe filename component."""
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:50]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Parse the base CV once
    log.info("Parsing base CV: %s", BASE_CV_PATH)
    doc = Document(BASE_CV_PATH)
    sections = find_sections(doc)
    original_content = {
        name: extract_section_text(doc, info)
        for name, info in sections.items()
    }

    log.info("Sections found: %s", list(sections.keys()))
    log.info("Mutable sections: %s", [s for s in sections if s in MUTABLE_SECTIONS])

    # 2. Get approved jobs from database
    session = SessionLocal()
    try:
        jobs = session.query(Job).filter(Job.status == "ready").all()
        if not jobs:
            log.info("No ready jobs found in database.")
            return

        log.info("Processing %d ready job(s)...", len(jobs))

        for i, job in enumerate(jobs, 1):
            label = f"[{i}/{len(jobs)}] {job.title} @ {job.company}"

            if not job.description:
                log.warning("%s — skipped (no description)", label)
                continue

            log.info("%s — tailoring...", label)

            try:
                # 3. Tailor with Gemini
                tailored = tailor_cv(original_content, job)

                # 4. Write the tailored .docx
                company = sanitize_filename(job.company or "unknown")
                title = sanitize_filename(job.title or "unknown")
                filename = f"{company}_{title}_talasli_cv.docx"
                output_path = os.path.join(OUTPUT_DIR, filename)

                write_tailored_cv(BASE_CV_PATH, output_path, tailored)

                # 5. Update status
                job.status = "cv_generated"
                session.commit()
                log.info("%s — saved: %s", label, output_path)

            except Exception as e:
                session.rollback()
                log.error("%s — failed: %s", label, e, exc_info=True)

            # Rate-limit: stay under Gemini free-tier (15 RPM)
            if i < len(jobs):
                time.sleep(4)

    finally:
        session.close()

    log.info("Done.")


generate_cvs_for_ready_jobs = main

if __name__ == "__main__":
    main()
