import json
import os
from pathlib import Path
from typing import List, Dict, Any

class StorageManager:
    """
    Handles saving and loading scraped job postings and application records locally.
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.data_dir / "scraped_jobs.json"

    def save_jobs(self, new_jobs: List[Dict[str, Any]]) -> str:
        """
        Saves a list of scraped jobs into a local JSON file without duplicates.
        """
        existing_jobs = self.load_jobs()

        # Avoid duplicate jobs by link/job_id
        existing_ids = {j.get("job_id") or j.get("link") for j in existing_jobs if j.get("job_id") or j.get("link")}

        added_count = 0
        for job in new_jobs:
            identifier = job.get("job_id") or job.get("link")
            if identifier not in existing_ids:
                existing_jobs.append(job)
                existing_ids.add(identifier)
                added_count += 1

        with open(self.jobs_file, "w", encoding="utf-8") as f:
            json.dump(existing_jobs, f, indent=2, ensure_ascii=False)

        print(f"Saved {added_count} new job listings! (Total stored: {len(existing_jobs)})")
        return str(self.jobs_file)

    def load_jobs(self) -> List[Dict[str, Any]]:
        """Loads all stored jobs from the local JSON file."""
        if not self.jobs_file.exists():
            return []
        try:
            with open(self.jobs_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
