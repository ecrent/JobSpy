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
Master's in Computer Engineering — present this career transition as a strength.
6. When mentioning AI-assisted development skills, NEVER name specific products \
(no Copilot, no Claude, no ChatGPT, no Cursor). Instead say "coding agents", \
"LLM-assisted development", "AI coding tools", or similar generic terms.
7. The entire CV must fit on ONE page — keep everything concise."""

SUMMARY_PREFIX = (
    "Results-driven professional translating 7 years of rigorous engineering "
    "problem-solving into Full-Stack Software Development. Currently completing "
    "an MSc in Computer Engineering with hands-on expertise"
)

FIXED_PROJECTS = [
    "Designed and implemented (Master's Thesis) a 'JWT Decoupling Strategy' within a polyglot Google Cloud Microservices environment to optimize high-traffic network bottlenecks. Achieved a 15% reduction in network traffic and significantly improved system performance, reducing average gRPC latency by 50% and P99 tail latency by 25% through meticulous A/B testing and gRPC Interceptor integration.",
    "Developed and deployed a full-stack web application to AWS, implementing robust authentication, secure network traffic, and comprehensive metric monitoring. This project showcased end-to-end development, API-first principles, and foundational DevOps practices for rapid iteration and deployment.",
    "Engineered a scalable, end-to-end data pipeline utilizing Kafka, Spark, and Elasticsearch for real-time processing and big data storage of e-commerce analytics. Containerized the entire system with Docker, demonstrating robust automation capabilities and efficient data management.",
    "Built an AI-powered job application assistant using Java with LangChain4j and Spring Boot, integrating LLM-based agents to automatically parse job descriptions, tailor resumes, and generate personalized cover letters. Leveraged retrieval-augmented generation (RAG) with a vector store to match candidate skills against job requirements.",
]


def _build_prompt(original_content, job):
    """Build the tailoring prompt from original CV content and job data."""
    skills = "\n".join(original_content.get("TECHNICAL SKILLS", []))

    job_meta = f"Title: {job.title or 'N/A'}\nCompany: {job.company or 'N/A'}"
    if job.job_level:
        job_meta += f"\nLevel: {job.job_level}"
    if job.company_industry:
        job_meta += f"\nIndustry: {job.company_industry}"
    if job.job_function:
        job_meta += f"\nFunction: {job.job_function}"

    return f"""\
Tailor the following CV sections for the target job below.

═══ CANDIDATE INFO ═══

The candidate's known tech stack: C#, JavaScript, Python, HTML5/CSS3, .NET (ASP.NET Core, EF Core), \
React.js, Node.js, RESTful APIs, MS SQL Server, PostgreSQL, NoSQL, Elasticsearch, Kafka, Apache Spark, \
AWS, Docker, Kubernetes, Git/GitHub, CI/CD, gRPC, JWT, Google Cloud.

Current Technical Skills section:
{skills}

Fixed projects (for context — DO NOT modify these):
1. {FIXED_PROJECTS[0]}
2. {FIXED_PROJECTS[1]}
3. {FIXED_PROJECTS[2]}
4. {FIXED_PROJECTS[3]}

═══ TARGET JOB ═══
{job_meta}

Job Description:
{job.description}

═══ INSTRUCTIONS ═══

1. **PROFESSIONAL SUMMARY CONTINUATION** (1-2 SHORT sentences ONLY):
   The summary ALWAYS starts with this fixed prefix (do NOT include it in your output):
   "{SUMMARY_PREFIX}"
   
   Write ONLY the continuation that comes after "...with hands-on expertise".
   - It must start with " in" or a comma, connecting naturally to the prefix.
   - Mention relevant technologies from the job description (e.g., if they want Java, mention Java).
   - End with expressing genuine interest in the company's DOMAIN or SECTOR \
(e.g., "interested in electronic warfare systems", "interested in fintech solutions", \
"interested in defense technologies"). Derive this from the job description context.
   - Do NOT mention the company name. Express interest in the FIELD, not the company.
   - Keep it to 1-2 sentences MAX — the CV must fit on one page.
   - Keep it to 1-2 sentences MAX — the CV must fit on one page.

2. **FIFTH PROJECT** (1 entry only — 2-3 sentences):
   - Write ONE project description that aligns with what the job EXPECTS the candidate to DO \
(look for sections like "responsibilities", "what we expect", "what you'll do").
   - Focus on practical, everyday software development work (building UIs, APIs, improving \
existing systems, writing clean maintainable code) — NOT fancy simulations, threat monitoring, \
or overly complex scenarios.
   - Use technologies and skills mentioned in the job posting.
   - Make it realistic and simple — something a CS master's student would actually build.
   - Achievement-oriented with measurable results where possible.
   - Do NOT overlap with the 4 fixed projects above:
     * Project 1 covers: gRPC, JWT, microservices, Google Cloud, A/B testing
     * Project 2 covers: full-stack web app, AWS, authentication, DevOps
     * Project 3 covers: Kafka, Spark, Elasticsearch, data pipeline, Docker
     * Project 4 covers: LangChain4j, Spring Boot, LLM agents, RAG, vector store, AI
   - The fifth project must cover DIFFERENT technologies or a different type of work.

3. **TECHNICAL SKILLS** (exactly 4 lines, merged/compact to fit 1 page):
   - Line 1: "Programming Languages: ..." 
   - Line 2: "Frameworks & Libraries: ..."
   - Line 3: "Database Systems: ..." (can include data tools like Kafka, Spark here)
   - Line 4: "Cloud & DevOps: ..."
   - Mirror keywords/technologies from the job posting.
   - Include the candidate's real skills plus closely related ones a developer with this stack would know.
   - If mentioning AI skills, use generic terms only (coding agents, LLMs, AI coding tools). \
NEVER mention Copilot, Claude, ChatGPT, Cursor, or any specific AI product names.

Respond ONLY with valid JSON in this exact structure:
{{
  "summary_continuation": "in .NET and React... (the part after the fixed prefix)",
  "fifth_project": "Built a ... achieving ...",
  "technical_skills": {{
    "Programming Languages": "C#, JavaScript, ...",
    "Frameworks & Libraries": ".NET ..., React.js, ...",
    "Database Systems": "MS SQL Server, ...",
    "Cloud & DevOps": "AWS, Docker, ..."
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
            if "summary_continuation" not in result:
                raise ValueError("Missing 'summary_continuation' in response")
            if "fifth_project" not in result:
                raise ValueError("Missing 'fifth_project' in response")
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
