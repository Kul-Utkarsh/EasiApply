from sqlalchemy import Column, Integer, String, Float, Text, DateTime, create_engine, text, inspect, event
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
import os

def _utc_now():
    return datetime.now(timezone.utc)

Base = declarative_base()


class JobApplication(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), unique=True, index=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255))
    link = Column(Text)
    description = Column(Text, nullable=True)

    # Source: "jobs" (LinkedIn Jobs board) or "posts" (LinkedIn Posts feed)
    source_type = Column(String(20), default="jobs")
    contact_info = Column(Text, nullable=True)
    author_name = Column(String(255), nullable=True)
    author_profile_url = Column(Text, nullable=True)

    # Match and AI scoring
    match_score = Column(Float, default=0.0, index=True)
    match_reason = Column(Text, nullable=True)
    ats_score = Column(Float, default=0.0)
    ats_breakdown = Column(Text, nullable=True)

    # Tailored artifacts
    tailored_resume_text = Column(Text, nullable=True)
    missing_keywords = Column(Text, nullable=True)
    email_draft_subject = Column(String(255), nullable=True)
    email_draft_body = Column(Text, nullable=True)
    linkedin_note = Column(Text, nullable=True)

    # Lifecycle status
    status = Column(String(50), default="Scraped", index=True)

    # Tracking metadata
    notes = Column(Text, nullable=True)
    resume_used = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utc_now, index=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)


class OutboxEmail(Base):
    """Throttled auto-send queue — one SMTP transaction per row, never bulk."""
    __tablename__ = "outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(Integer, index=True)
    to_email = Column(String(255), nullable=False)
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    attachment_path = Column(Text, nullable=True)
    # queued | sending | sent | failed | cancelled
    status = Column(String(20), default="queued", index=True)
    attempts = Column(Integer, default=0)
    scheduled_at = Column(DateTime, default=_utc_now)
    sent_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now)


_DB_SESSION_FACTORIES = {}

def init_db(db_path="./data/applications.db"):
    abs_path = os.path.abspath(db_path)
    if abs_path in _DB_SESSION_FACTORIES:
        return _DB_SESSION_FACTORIES[abs_path]()

    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    engine = create_engine(
        f"sqlite:///{abs_path}",
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30.0}
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        finally:
            cursor.close()

    # Safe lightweight SQLite migration: check existing columns and add any missing ones
    try:
        with engine.connect() as conn:
            inspector = inspect(engine)
            if "applications" in inspector.get_table_names():
                existing_columns = [col["name"] for col in inspector.get_columns("applications")]

                new_columns = {
                    "source_type": "VARCHAR(20) DEFAULT 'jobs'",
                    "contact_info": "TEXT",
                    "author_name": "VARCHAR(255)",
                    "author_profile_url": "TEXT",
                    "tailored_resume_text": "TEXT",
                    "missing_keywords": "TEXT",
                    "ats_score": "FLOAT DEFAULT 0.0",
                    "ats_breakdown": "TEXT",
                    "email_draft_subject": "VARCHAR(255)",
                    "email_draft_body": "TEXT",
                    "linkedin_note": "TEXT",
                    "resume_used": "VARCHAR(255)"
                }

                for col_name, col_type in new_columns.items():
                    if col_name not in existing_columns:
                        try:
                            conn.execute(text(f"ALTER TABLE applications ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                        except Exception as migration_err:
                            print(f"Migration notice for {col_name}: {migration_err}")

            if "outbox" in inspector.get_table_names():
                existing_outbox_columns = [col["name"] for col in inspector.get_columns("outbox")]
                new_outbox_columns = {
                    "attachment_path": "TEXT",
                    "attempts": "INTEGER DEFAULT 0",
                    "scheduled_at": "DATETIME",
                    "sent_at": "DATETIME",
                    "error": "TEXT"
                }
                for col_name, col_type in new_outbox_columns.items():
                    if col_name not in existing_outbox_columns:
                        try:
                            conn.execute(text(f"ALTER TABLE outbox ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                        except Exception as migration_err:
                            print(f"Migration notice for outbox.{col_name}: {migration_err}")

            # Ensure indexes exist on key query columns for existing DB files
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status)",
                "CREATE INDEX IF NOT EXISTS idx_apps_created ON applications(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_apps_updated ON applications(updated_at)",
                "CREATE INDEX IF NOT EXISTS idx_apps_score ON applications(match_score)"
            ]:
                try:
                    conn.execute(text(idx_sql))
                    conn.commit()
                except Exception:
                    pass
    except Exception as e:
        print(f"DB inspection warning: {e}")

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    _DB_SESSION_FACTORIES[abs_path] = session_factory
    return session_factory()
