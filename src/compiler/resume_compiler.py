from pathlib import Path
import subprocess
import tempfile
import os
import sys
import html
from docx import Document

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

class ResumeCompiler:
    """
    Converts a structured Markdown resume into styled PDF/DOCX documents.
    """

    def __init__(self, template_dir="./templates"):
        self.template_dir = Path(template_dir)

    def compile_to_pdf(self, markdown_content: str, output_path: str) -> bool:
        """
        Renders a Markdown resume to a professional PDF.
        Priority order: Typst (if installed) -> Chromium (via Playwright) -> LibreOffice fallback.
        """
        md_path = None
        typ_path = None
        try:
            # Write markdown to temporary file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
                f.write(markdown_content)
                md_path = f.name

            # Convert to Typst template
            typst_template = self._markdown_to_typst_template(markdown_content)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".typ", delete=False, encoding="utf-8") as f:
                f.write(typst_template)
                typ_path = f.name

            # Compile with Typst (if available)
            subprocess.run(
                ["typst", "compile", typ_path, output_path],
                check=True,
                capture_output=True,
                timeout=30
            )
            print(f"[INFO] PDF compiled using Typst: {output_path}")
            return True

        except (subprocess.CalledProcessError, FileNotFoundError):
            # Typst not installed, use Playwright Chromium native PDF generator
            if self._render_pdf_with_chromium(markdown_content, output_path):
                return True
            # Secondary fallback: LibreOffice
            return self._fallback_docx_to_pdf(markdown_content, output_path)
        finally:
            for tmp in [md_path, typ_path]:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)

    def _render_pdf_with_chromium(self, markdown_content: str, output_path: str) -> bool:
        """
        Converts markdown into styled HTML and uses Playwright Chromium to print to PDF.
        Runs locally on Windows with zero external tools needed.
        """
        try:
            from playwright.sync_api import sync_playwright

            html_lines = []
            for line in markdown_content.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("# "):
                    html_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
                elif line.startswith("## "):
                    html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
                elif line.startswith("### "):
                    html_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
                elif line.startswith("- ") or line.startswith("* "):
                    html_lines.append(f"<li>{html.escape(line[2:])}</li>")
                else:
                    html_lines.append(f"<p>{html.escape(line)}</p>")

            html_body = "\n".join(html_lines)
            full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    line-height: 1.45;
    color: #111;
    margin: 20mm;
    font-size: 10pt;
  }}
  h1 {{ font-size: 18pt; margin-bottom: 4px; color: #000; border-bottom: 2px solid #333; padding-bottom: 4px; }}
  h2 {{ font-size: 13pt; margin-top: 14px; margin-bottom: 4px; color: #222; border-bottom: 1px solid #ccc; padding-bottom: 2px; }}
  h3 {{ font-size: 11pt; margin-top: 8px; margin-bottom: 2px; color: #333; }}
  p {{ margin: 4px 0; }}
  li {{ margin: 2px 0 2px 18px; }}
  @page {{ size: A4; margin: 10mm; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(full_html, wait_until="load")
                page.pdf(path=output_path, format="A4", print_background=True)
                browser.close()
            print(f"[INFO] PDF created via Chromium: {output_path}")
            return True
        except Exception as e:
            print(f"[WARN] Chromium PDF rendering notice: {e}")
            return False

    def compile_to_docx(self, markdown_content: str, output_path: str) -> bool:
        """
        Creates a professional DOCX file from the Markdown content using python-docx.
        """
        doc = Document()
        # Parse Markdown sections and add to DOCX
        lines = markdown_content.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Header detection
            if line.startswith("# "):
                doc.add_heading(line[2:], level=1)
            elif line.startswith("## "):
                doc.add_heading(line[3:], level=2)
            elif line.startswith("### "):
                doc.add_heading(line[4:], level=3)
            else:
                # Bullet points
                if line.startswith("- "):
                    p = doc.add_paragraph(style="ListBullet")
                    p.add_run(line[2:])
                else:
                    doc.add_paragraph(line)
        try:
            doc.save(output_path)
            print(f"✅ DOCX saved: {output_path}")
            return True
        except Exception as e:
            print(f"Error saving DOCX: {e}")
            return False

    def _markdown_to_typst_template(self, markdown_content: str) -> str:
        """
        Convert Markdown content into a Typst template with a clean design.
        """
        template = f"""
#set page(
  width: 8.5in,
  height: 11in,
  margin: (top: 0.5in, bottom: 0.5in, left: 0.5in, right: 0.5in),
)
#set text(size: 10pt, font: "Times New Roman")

{markdown_content}
"""
        return template

    def _fallback_docx_to_pdf(self, markdown_content: str, pdf_output_path: str) -> bool:
        """
        Generates a DOCX file first, then converts to PDF (via LibreOffice if available).
        """
        # Step 1: Generate DOCX file
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            docx_path = tmp_docx.name
            if not self.compile_to_docx(markdown_content, docx_path):
                return False

        # Step 2: Convert DOCX to PDF using LibreOffice (if installed)
        try:
            subprocess.run(
                ["soffice", "--convert-to", "pdf", docx_path, "--outdir", os.path.dirname(pdf_output_path)],
                check=True,
                capture_output=True,
                timeout=45
            )
            # Rename to target name
            generated_pdf = docx_path.replace(".docx", ".pdf")
            if os.path.exists(generated_pdf):
                os.rename(generated_pdf, pdf_output_path)
                print(f"✅ PDF created via LibreOffice: {pdf_output_path}")
                return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️ LibreOffice not available. PDF creation skipped; only DOCX saved.")
            # At least we have the DOCX as fallback
            return False
        finally:
            if os.path.exists(docx_path):
                os.unlink(docx_path)
        return False
