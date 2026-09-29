import os
from pathlib import Path
from typing import List, Dict, Optional


class ResumeManager:
    """
    Manages multiple resume files (PDF, DOCX, Markdown, TXT) in data/resumes/
    """

    def __init__(self, resumes_dir: str = "./data/resumes"):
        self.resumes_dir = Path(resumes_dir)
        self.resumes_dir.mkdir(parents=True, exist_ok=True)

    def list_resumes(self) -> List[str]:
        """Returns list of all available resume filenames."""
        files = []
        for f in self.resumes_dir.glob("*.*"):
            if f.suffix.lower() in [".md", ".txt", ".docx", ".pdf"]:
                files.append(f.name)
        return sorted(files)

    def save_uploaded_file(self, uploaded_file) -> str:
        """Saves an uploaded file to data/resumes/.
        Accepts Streamlit UploadedFile or FastAPI UploadFile.
        """
        # Streamlit uses .name + .getbuffer(); FastAPI uses .filename + .file
        filename = getattr(uploaded_file, "filename", None) or getattr(uploaded_file, "name", "resume.bin")
        dest_path = self.resumes_dir / filename
        with open(dest_path, "wb") as f:
            if hasattr(uploaded_file, "getbuffer"):
                f.write(uploaded_file.getbuffer())
            elif hasattr(uploaded_file, "file"):
                f.write(uploaded_file.file.read())
            else:
                # Async FastAPI UploadFile: caller should pass bytes already
                content = uploaded_file.read() if hasattr(uploaded_file, "read") else b""
                f.write(content)
        return str(dest_path)

    def get_resume_text(self, filename: str) -> str:
        """Reads and extracts plain text from a resume file."""
        if filename == "base_resume.md":
            path = Path("./data/base_resume.md")
        else:
            path = self.resumes_dir / filename

        if not path.exists():
            return "Resume not found."

        suffix = path.suffix.lower()

        # Markdown or TXT
        if suffix in [".md", ".txt"]:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        # Word Document (.docx)
        elif suffix == ".docx":
            try:
                from docx import Document
                doc = Document(str(path))
                lines = [p.text for p in doc.paragraphs if p.text]
                for table in doc.tables:
                    for row in table.rows:
                        row_data = [cell.text for cell in row.cells if cell.text]
                        if row_data:
                            lines.append(" | ".join(row_data))
                return "\n".join(lines)
            except Exception as e:
                return f"Error reading DOCX: {e}"

        # PDF file (.pdf)
        elif suffix == ".pdf":
            try:
                # Try pypdf or pdfplumber if available, otherwise read binary preview
                import pypdf
                reader = pypdf.PdfReader(str(path))
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                return text if text else "Could not extract text from PDF."
            except Exception:
                return f"PDF uploaded ({filename}). Note: Install pypdf for full text extraction or upload as .md/.docx."

        return "Unsupported format."
