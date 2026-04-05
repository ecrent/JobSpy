import os
from datetime import datetime

from dotenv import load_dotenv
from jobspy import scrape_jobs
from sqlalchemy.dialects.postgresql import insert

from db import Job, SessionLocal, init_db

load_dotenv()

# Load proxies
proxy_str = os.getenv("PROXIES", "")
proxies = [p.strip() for p in proxy_str.split(",") if p.strip()]
print(f"Loaded {len(proxies)} proxies")

SEARCH_TERMS = ["YAZILIM", "DEVELOPER", "GAME", "JAVA", "IT"]
LOCATION = "Ankara"

# Skip jobs with these words in the title
SENIOR_KEYWORDS = {"senior", "sr.", "lead", "principal", "staff", "director", "manager", "head"}
INTERN_KEYWORDS = {"internship", "intern", "stajyer", "staj"}
SKIP_KEYWORDS = SENIOR_KEYWORDS | INTERN_KEYWORDS


def _should_skip(title: str) -> bool:
    """Return True if the title is a senior-level or internship position."""
    if not title:
        return False
    words = title.lower().split()
    return bool(SKIP_KEYWORDS & set(words))


def scrape_and_store(
    search_term: str,
    location: str,
    results_wanted: int = 50,
    is_remote: bool = False,
    site_name: str = "linkedin",
):
    """Scrape jobs and insert into the database, skipping duplicates and senior roles."""
    print(f"\nScraping: '{search_term}' in '{location}' (remote={is_remote}, wanted={results_wanted})")

    jobs_df = scrape_jobs(
        site_name=site_name,
        search_term=search_term,
        location=location,
        results_wanted=results_wanted,
        is_remote=is_remote,
        linkedin_fetch_description=True,
        proxies=proxies if proxies else None,
    )

    if jobs_df.empty:
        print("No jobs found.")
        return 0

    print(f"Scraped {len(jobs_df)} jobs. Filtering and inserting...")

    session = SessionLocal()
    inserted = 0
    skipped = 0
    filtered = 0

    try:
        for _, row in jobs_df.iterrows():
            title = row.get("title") or ""

            # Skip senior-level and internship positions
            if _should_skip(title):
                filtered += 1
                continue

            # Parse location string "City, State, Country" into parts
            loc_str = str(row.get("location", "")) if row.get("location") else ""
            loc_parts = [p.strip() for p in loc_str.split(",")]
            city = loc_parts[0] if len(loc_parts) >= 1 else None
            state = loc_parts[1] if len(loc_parts) >= 2 else None
            country = loc_parts[2] if len(loc_parts) >= 3 else None

            # Parse job_type list to string
            job_type = row.get("job_type")
            if isinstance(job_type, list):
                job_type = ", ".join(str(jt) for jt in job_type)
            elif job_type:
                job_type = str(job_type)

            job_url = str(row.get("job_url", ""))
            if not job_url:
                continue

            stmt = insert(Job).values(
                site=site_name,
                scraped_at=datetime.utcnow(),
                title=title,
                company=row.get("company"),
                company_url=row.get("company_url"),
                job_url=job_url,
                location_city=city,
                location_state=state,
                location_country=country,
                is_remote=bool(row.get("is_remote")) if row.get("is_remote") is not None else None,
                description=row.get("description"),
                job_type=job_type,
                job_level=row.get("job_level"),
                company_industry=row.get("company_industry"),
                job_function=row.get("job_function"),
                date_posted=row.get("date_posted"),
                status="new",
            ).on_conflict_do_nothing(constraint="uq_job_url")

            result = session.execute(stmt)
            if result.rowcount:
                inserted += 1
            else:
                skipped += 1

        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

    print(f"Done: {inserted} inserted, {skipped} duplicates skipped, {filtered} filtered out (senior/intern)")
    return inserted


if __name__ == "__main__":
    init_db()

    for term in SEARCH_TERMS:
        # Location-based search (Ankara)
        scrape_and_store(search_term=term, location=LOCATION, results_wanted=5)
        # Remote search
        scrape_and_store(search_term=term, location="Turkey", results_wanted=5, is_remote=True)
