"""Use Google Gemini to tailor CV sections for a specific job posting."""

import json
import logging
import os
import time

from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

log = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """\
You are an expert CV/resume tailoring assistant. You adapt specific CV sections \
to match job descriptions while keeping content truthful and professional.

RULES:
1. NEVER fabricate work experience or education.
2. NEVER change the candidate's actual background facts.
3. Use keywords, terminology, and phrasing from the job description.
4. Keep the tone professional, concise, and achievement-oriented.
5. The candidate has a petroleum engineering background and is completing a \
Master's in Computer Engineering — present this career transition as a strength \
(cross-domain problem solving, engineering mindset)."""


def _build_prompt(original_content, job):
    """Build the tailoring prompt from original CV content and job data."""
    summary = "\n".join(original_content.get("PROFESSIONAL SUMMARY", []))
    projects = "\n\n".join(original_content.get("PROJECTS", []))
    skills = "\n".join(original_content.get("TECHNICAL SKILLS", []))
    education = "\n".join(original_content.get("EDUCATION", []))
    experience = "\n".join(original_content.get("EXPERIENCE", []))

    job_meta = f"Title: {job.title or 'N/A'}\nCompany: {job.company or 'N/A'}"
    if job.job_level:
        job_meta += f"\nLevel: {job.job_level}"
    if job.company_industry:
        job_meta += f"\nIndustry: {job.company_industry}"
    if job.job_function:
        job_meta += f"\nFunction: {job.job_function}"

    return f"""\
Tailor the following CV sections for the target job below.

═══ CANDIDATE'S CURRENT CV ═══

PROFESSIONAL SUMMARY:
{summary}

PROJECTS:
{projects}

TECHNICAL SKILLS:
{skills}

EDUCATION (context only — DO NOT modify):
{education}

EXPERIENCE (context only — DO NOT modify):
{experience}

═══ TARGET JOB ═══
{job_meta}

Job Description:
{job.description}

═══ INSTRUCTIONS ═══

1. **PROFESSIONAL SUMMARY** (2-3 sentences):
   - Rewrite to align with this specific role.
   - Use keywords from the job description naturally.
   - Mention the candidate's engineering background and CS master's degree as strengths.

2. **PROJECTS** (3-5 entries):
   - Rewrite existing projects to emphasize technologies and skills relevant to this job.
   - You may add 1-2 new realistic project descriptions based on the candidate's known \
tech stack (Python, C#, .NET, React, AWS, Docker, Kafka, Spark, Elasticsearch, gRPC, Kubernetes).
   - Each project: 1-3 sentences, achievement-oriented with measurable results where possible.
   - If a project has a distinct name/title, include it. Otherwise leave title as empty string.

3. **TECHNICAL SKILLS** (4-6 categories):
   - Mirror the exact technologies and keywords from the job posting.
   - Group into categories like "Programming Languages", "Frameworks & Libraries", \
"Database Systems", "Tools & Platforms", "Cloud & DevOps", etc.
   - Include technologies the candidate actually knows plus closely related ones that a \
developer with this stack would reasonably know.

Respond ONLY with valid JSON in this exact structure:
{{
  "professional_summary": "The tailored summary text",
  "projects": [
    {{"title": "Project Title or empty string", "description": "Project description text"}},
    ...
  ],
  "technical_skills": {{
    "Category Name": "comma-separated skills list",
    ...
  }}
}}"""


def tailor_cv(original_content, job, max_retries=3):
    """Call Gemini to tailor CV sections for a job. Returns parsed JSON dict."""
    prompt = _build_prompt(original_content, job)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_INSTRUCTION,
                    "response_mime_type": "application/json",
                    "temperature": 0.7,
                },
            )
            result = json.loads(response.text)

            # Validate structure
            if "professional_summary" not in result:
                raise ValueError("Missing 'professional_summary' in response")
            if not isinstance(result.get("projects"), list):
                raise ValueError("'projects' must be a list")
            if not isinstance(result.get("technical_skills"), dict):
                raise ValueError("'technical_skills' must be a dict")

            return result

        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt * 5
                log.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
