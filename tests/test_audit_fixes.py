import unittest
import os
import tempfile
from pathlib import Path
from src.storage.db import DatabaseManager
from src.storage.models import JobApplication, OutboxEmail, _DB_SESSION_FACTORIES

class TestAuditFixes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_audit.db")
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        abs_p = os.path.abspath(self.db_path)
        if abs_p in _DB_SESSION_FACTORIES:
            factory = _DB_SESSION_FACTORIES.pop(abs_p)
            factory.kw['bind'].dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_database_clear_and_cascade_delete(self):
        session = self.db.get_session()
        # Seed application and related outbox email
        app = JobApplication(
            job_id="test-job-999",
            title="Senior UX Engineer",
            company="Tech Corp",
            source_type="posts"
        )
        session.add(app)
        session.commit()
        app_id = app.id

        email = OutboxEmail(
            app_id=app_id,
            to_email="recruiter@techcorp.com",
            subject="Application for Senior UX Engineer",
            body="Hello, I am interested.",
            status="queued"
        )
        session.add(email)
        session.commit()
        session.close()

        # 1. Verify delete_application cascades OutboxEmail
        self.db.delete_application(app_id)
        session = self.db.get_session()
        remaining_app = session.query(JobApplication).filter_by(id=app_id).first()
        remaining_email = session.query(OutboxEmail).filter_by(app_id=app_id).first()
        session.close()

        self.assertIsNone(remaining_app)
        self.assertIsNone(remaining_email)

        # 2. Verify clear_all_applications works cleanly without NameError
        session = self.db.get_session()
        session.add(JobApplication(job_id="test-2", title="PM", company="Co"))
        session.commit()
        session.close()

        try:
            self.db.clear_all_applications()
        except NameError as e:
            self.fail(f"clear_all_applications raised NameError: {e}")

        apps = self.db.get_all_applications()
        self.assertEqual(len(apps), 0)

    def test_session_expire_on_commit_is_false(self):
        session = self.db.get_session()
        app = JobApplication(
            job_id="test-expire-check",
            title="Data Scientist",
            company="AI Labs"
        )
        session.add(app)
        session.commit()
        app_id = app.id
        session.close()

        # Reading application should not raise DetachedInstanceError
        fetched = self.db.get_application(app_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Data Scientist")


if __name__ == "__main__":
    unittest.main()
