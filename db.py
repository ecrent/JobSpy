import os
from datetime import datetime, date

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Date,
    DateTime,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Source
    site = Column(String(50))
    scraped_at = Column(DateTime, default=datetime.utcnow)

    # Core fields
    title = Column(String(500))
    company = Column(String(300))
    company_url = Column(Text)
    job_url = Column(Text, nullable=False)
    job_url_direct = Column(Text)

    # Location
    location_city = Column(String(200))
    location_state = Column(String(200))
    location_country = Column(String(200))
    is_remote = Column(Boolean)

    # Job details
    description = Column(Text)
    job_type = Column(String(100))
    job_level = Column(String(100))
    company_industry = Column(String(300))
    job_function = Column(String(200))
    date_posted = Column(Date)

    # Compensation
    compensation_min = Column(Float)
    compensation_max = Column(Float)
    compensation_currency = Column(String(10))
    compensation_interval = Column(String(20))

    # Extra
    emails = Column(Text)
    company_logo = Column(Text)

    # Pipeline status: new → approved → cv_generated → applied → interview / rejected
    status = Column(String(20), default="new")

    __table_args__ = (
        UniqueConstraint("job_url", name="uq_job_url"),
    )


def init_db():
    """Create all tables."""
    Base.metadata.create_all(engine)
    print("Database tables created successfully.")


if __name__ == "__main__":
    init_db()
