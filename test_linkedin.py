import csv
import os
from dotenv import load_dotenv
from jobspy import scrape_jobs
import pandas as pd

load_dotenv()

# Load proxies from .env
proxy_str = os.getenv("PROXIES", "")
proxies = [p.strip() for p in proxy_str.split(",") if p.strip()]
print(f"Loaded {len(proxies)} proxies")

pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", 200)
pd.set_option("display.width", 300)

# Test 1: Software developer jobs in Ankara
print("=" * 80)
print("TEST 1: Software Developer jobs in Ankara, Turkey")
print("=" * 80)

jobs_ankara = scrape_jobs(
    site_name="linkedin",
    search_term="software developer",
    location="Ankara, Turkey",
    results_wanted=10,
    linkedin_fetch_description=True,
    proxies=proxies,
)

print(f"\nFound {len(jobs_ankara)} jobs in Ankara:")
if not jobs_ankara.empty:
    cols = ["title", "company", "location", "date_posted", "job_url", "description", "job_type", "job_level", "company_industry", "job_function", "job_url_direct"]
    cols = [c for c in cols if c in jobs_ankara.columns]
    print(jobs_ankara[cols].to_string(index=False))

# Test 2: Remote software developer jobs
print("\n" + "=" * 80)
print("TEST 2: Remote Software Developer jobs")
print("=" * 80)

jobs_remote = scrape_jobs(
    site_name="linkedin",
    search_term="software developer",
    location="Turkey",
    is_remote=True,
    results_wanted=10,
    linkedin_fetch_description=True,
    proxies=proxies,
)

print(f"\nFound {len(jobs_remote)} remote jobs:")
if not jobs_remote.empty:
    cols = ["title", "company", "location", "date_posted", "job_url", "description", "job_type", "job_level", "company_industry", "job_function", "job_url_direct"]
    cols = [c for c in cols if c in jobs_remote.columns]
    print(jobs_remote[cols].to_string(index=False))

# Save to CSV for easier reading
all_jobs = pd.concat([jobs_ankara, jobs_remote], ignore_index=True)
all_jobs.to_csv("jobs_results.csv", quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
print(f"\n\nDone! Saved {len(all_jobs)} jobs to jobs_results.csv")
