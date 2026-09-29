from src.storage.models import JobApplication, OutboxEmail, init_db
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
import os

def _utc_now():
    return datetime.now(timezone.utc)


class DatabaseManager:
    def __init__(self, db_path="./data/applications.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_session(self):
        return init_db(self.db_path)

    def upsert_scraped_jobs(self, jobs: List[Dict[str, Any]]) -> int:
        session = self.get_session()
        added_count = 0
        try:
            target_ids = [j.get("job_id") or j.get("link") for j in jobs if (j.get("job_id") or j.get("link"))]
            existing_map = {}
            if target_ids:
                existing_apps = session.query(JobApplication).filter(JobApplication.job_id.in_(target_ids)).all()
                existing_map = {a.job_id: a for a in existing_apps}

            for job_data in jobs:
                job_id = job_data.get("job_id") or job_data.get("link")
                if not job_id:
                    continue

                existing = existing_map.get(job_id)
                if not existing:
                    app = JobApplication(
                        job_id=job_id,
                        title=job_data.get("title", "Unknown Title"),
                        company=job_data.get("company", "Unknown Company"),
                        location=job_data.get("location", "Unknown Location"),
                        link=job_data.get("link", ""),
                        description=job_data.get("description", ""),
                        source_type=job_data.get("source_type", "jobs"),
                        contact_info=job_data.get("contact_info", ""),
                        author_name=job_data.get("author_name", ""),
                        author_profile_url=job_data.get("author_profile_url", ""),
                        status="Scraped"
                    )
                    session.add(app)
                    added_count += 1
                else:
                    # Update existing record if new info is available
                    if job_data.get("description") and not existing.description:
                        existing.description = job_data["description"]
                    if job_data.get("contact_info") and not existing.contact_info:
                        existing.contact_info = job_data["contact_info"]
                    if job_data.get("author_profile_url") and not getattr(existing, "author_profile_url", None):
                        existing.author_profile_url = job_data["author_profile_url"]
                    if job_data.get("link") and existing.link in (None, "", "https://www.linkedin.com/feed/"):
                        existing.link = job_data["link"]
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Database error: {e}")
        finally:
            session.close()

        return added_count

    def get_existing_job_hashes(self) -> set:
        """
        Returns a set of existing job_ids, canonical post URLs, and content fingerprints
        to allow instantaneous O(1) cross-session duplicate checks while scrolling.
        """
        session = self.get_session()
        hashes = set()
        try:
            records = session.query(
                JobApplication.job_id,
                JobApplication.link,
                JobApplication.author_name,
                JobApplication.title,
                JobApplication.description
            ).all()
            for r in records:
                if r[0]:
                    hashes.add(str(r[0]).strip())
                if r[1] and r[1] != "https://www.linkedin.com/feed/":
                    clean_link = r[1].split("?")[0].rstrip("/")
                    hashes.add(clean_link)
                # Content fingerprint: (author or title) + first 80 chars of description
                author_or_title = (r[2] or r[3] or "").strip().lower()
                desc_snip = (r[4] or "")[:80].strip().lower()
                if author_or_title or desc_snip:
                    hashes.add(f"{author_or_title}::{desc_snip}")
            return hashes
        except Exception as e:
            print(f"Error fetching existing job hashes: {e}")
            return set()
        finally:
            session.close()

    def get_all_applications(self) -> List[JobApplication]:
        session = self.get_session()
        try:
            return session.query(JobApplication).order_by(JobApplication.updated_at.desc()).all()
        finally:
            session.close()

    def get_application(self, app_id: int) -> JobApplication:
        session = self.get_session()
        try:
            return session.query(JobApplication).filter_by(id=app_id).first()
        finally:
            session.close()

    def update_application(self, app_id: int, **kwargs):
        session = self.get_session()
        try:
            app = session.query(JobApplication).filter_by(id=app_id).first()
            if app:
                for key, value in kwargs.items():
                    if hasattr(app, key):
                        setattr(app, key, value)
                app.updated_at = _utc_now()
                session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error updating application {app_id}: {e}")
        finally:
            session.close()

    def delete_application(self, app_id: int):
        session = self.get_session()
        try:
            session.query(OutboxEmail).filter_by(app_id=app_id).delete()
            app = session.query(JobApplication).filter_by(id=app_id).first()
            if app:
                session.delete(app)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error deleting application {app_id}: {e}")
        finally:
            session.close()

    def clear_all_applications(self):
        """Delete all applications and queued outbox emails from the database"""
        session = self.get_session()
        try:
            session.query(OutboxEmail).delete()
            session.query(JobApplication).delete()
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error clearing applications: {e}")
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Outbox queue (throttled auto-send)
    # ------------------------------------------------------------------
    def queue_email(self, app_id: int, to_email: str, subject: str, body: str,
                    attachment_path: Optional[str] = None,
                    scheduled_at: Optional[datetime] = None) -> int:
        session = self.get_session()
        try:
            row = OutboxEmail(app_id=app_id, to_email=to_email, subject=subject,
                              body=body, attachment_path=attachment_path,
                               status="queued", scheduled_at=scheduled_at or _utc_now())
            session.add(row)
            session.commit()
            return row.id
        finally:
            session.close()

    def get_due_outbox(self, limit: int = 5):
        session = self.get_session()
        try:
            rows = (session.query(OutboxEmail)
                    .filter(OutboxEmail.status == "queued",
                            OutboxEmail.scheduled_at <= _utc_now(),
                            OutboxEmail.attempts < 5)
                    .order_by(OutboxEmail.scheduled_at).limit(limit).all())
            # detach plain dicts before close
            return [{"id": r.id, "app_id": r.app_id, "to_email": r.to_email,
                     "subject": r.subject, "body": r.body,
                     "attachment_path": r.attachment_path, "attempts": r.attempts}
                    for r in rows]
        finally:
            session.close()

    def get_outbox(self, status: Optional[str] = None, limit: int = 100):
        session = self.get_session()
        try:
            q = session.query(OutboxEmail).order_by(OutboxEmail.id.desc())
            if status:
                q = q.filter(OutboxEmail.status == status)
            rows = q.limit(limit).all()
            return [{"id": r.id, "app_id": r.app_id, "to_email": r.to_email,
                     "subject": r.subject, "status": r.status,
                     "attempts": r.attempts,
                     "scheduled_at": r.scheduled_at.strftime("%Y-%m-%d %H:%M") if r.scheduled_at else "",
                     "sent_at": r.sent_at.strftime("%Y-%m-%d %H:%M") if r.sent_at else "",
                     "error": r.error or ""} for r in rows]
        finally:
            session.close()

    def mark_outbox(self, row_id: int, **kwargs):
        session = self.get_session()
        try:
            row = session.query(OutboxEmail).filter_by(id=row_id).first()
            if row:
                for key, value in kwargs.items():
                    if hasattr(row, key):
                        setattr(row, key, value)
                session.commit()
        finally:
            session.close()

    def count_sent_today(self) -> int:
        session = self.get_session()
        try:
            day_start = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
            return session.query(OutboxEmail).filter(
                OutboxEmail.status == "sent",
                OutboxEmail.sent_at >= day_start).count()
        finally:
            session.close()

    def last_sent_at(self):
        session = self.get_session()
        try:
            row = (session.query(OutboxEmail)
                    .filter(OutboxEmail.status == "sent")
                    .order_by(OutboxEmail.sent_at.desc()).first())
            return row.sent_at if row else None
        finally:
            session.close()

    def clear_outbox_queue(self) -> int:
        session = self.get_session()
        try:
            count = session.query(OutboxEmail).filter(OutboxEmail.status == "queued").delete()
            session.commit()
            return count
        except Exception as e:
            session.rollback()
            return 0
        finally:
            session.close()

    def get_sent_outbox(self, limit: int = 50):
        session = self.get_session()
        try:
            rows = (session.query(OutboxEmail)
                    .filter(OutboxEmail.status == "sent")
                    .order_by(OutboxEmail.sent_at.desc())
                    .limit(limit).all())
            return [{
                "id": r.id,
                "app_id": r.app_id,
                "to_email": r.to_email,
                "subject": r.subject,
                "status": r.status,
                "sent_at": r.sent_at.strftime("%Y-%m-%d %H:%M") if r.sent_at else "",
                "attachment": os.path.basename(r.attachment_path) if r.attachment_path else ""
            } for r in rows]
        finally:
            session.close()

    def recover_stranded_outbox(self, timeout_minutes: int = 5) -> int:
        """Reset emails stuck in 'sending' state (e.g. from crash or restart) back to 'queued'."""
        session = self.get_session()
        recovered = 0
        try:
            cutoff = _utc_now() - timedelta(minutes=timeout_minutes)
            stranded = (session.query(OutboxEmail)
                        .filter(OutboxEmail.status == "sending",
                                OutboxEmail.scheduled_at <= cutoff)
                        .all())
            for item in stranded:
                item.status = "queued"
                recovered += 1
            if recovered:
                session.commit()
            return recovered
        except Exception as e:
            session.rollback()
            print(f"Error recovering stranded outbox: {e}")
            return 0
        finally:
            session.close()
