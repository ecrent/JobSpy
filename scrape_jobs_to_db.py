import csv
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


def scrape_and_store(
    search_term: str,
    location: str,
    results_wanted: int = 50,
    is_remote: bool = False,
    site_name: str = "linkedin",
):
    """Scrape jobs and insert into the database, skipping duplicates."""
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

    print(f"Scraped {len(jobs_df)} jobs. Inserting into database...")

    session = SessionLocal()
    inserted = 0
    skipped = 0

    try:
        for _, row in jobs_df.iterrows():
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

            # Parse emails list to string
            emails = row.get("emails")
            if isinstance(emails, list):
                emails = ", ".join(emails)

            # Parse compensation
            comp_min = row.get("min_amount")
            comp_max = row.get("max_amount")
            comp_currency = row.get("currency")
            comp_interval = row.get("interval")

            job_url = str(row.get("job_url", ""))
            if not job_url:
                continue

            stmt = insert(Job).values(
                site=site_name,
                scraped_at=datetime.utcnow(),
                title=row.get("title"),
                company=row.get("company"),
                company_url=row.get("company_url"),
                job_url=job_url,
                job_url_direct=row.get("job_url_direct"),
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
                compensation_min=float(comp_min) if comp_min and str(comp_min) != "nan" else None,
                compensation_max=float(comp_max) if comp_max and str(comp_max) != "nan" else None,
                compensation_currency=str(comp_currency) if comp_currency and str(comp_currency) != "nan" else None,
                compensation_interval=str(comp_interval) if comp_interval and str(comp_interval) != "nan" else None,
                emails=emails,
                company_logo=row.get("company_logo"),
                status="new",
            ).on_conflict_do_nothing(constraint="uq_job_url")

            result = session.execute(stmt)
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        session.commit()
        print(f"Done: {inserted} new jobs inserted, {skipped} duplicates skipped.")
        return inserted

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    # Ensure tables exist
    init_db()

    # Scrape Ankara jobs
    scrape_and_store(
        search_term="software developer",
        location="Ankara, Turkey",
        results_wanted=150,
        is_remote=False,
    )

    # Scrape remote jobs for Turkey
    scrape_and_store(
        search_term="software developer",
        location="Turkey",
        results_wanted=150,
        is_remote=True,
    )

    # Print summary
    session = SessionLocal()
    total = session.query(Job).count()
    new_count = session.query(Job).filter(Job.status == "new").count()
    session.close()
    print(f"\n{'='*60}")
    print(f"Total jobs in database: {total}")
    print(f"New (awaiting review): {new_count}")
    print(f"{'='*60}")
    print("Go to Supabase dashboard → Table Editor → jobs to review!")
