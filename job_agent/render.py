"""Render a tailored resume to an actual file, one per job.

Produces a styled, print-ready HTML file (open it and Ctrl-P → Save as PDF).
If WeasyPrint is installed, a PDF is written too. The Markdown is always kept
alongside so nothing is lost if a renderer is unavailable.
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from job_agent.config import settings

_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 760px;
         margin: 40px auto; color: #1a1a1a; line-height: 1.5; padding: 0 24px; }}
  h1 {{ font-size: 26px; margin: 0 0 2px; }}
  h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: .06em;
        border-bottom: 1.5px solid #333; padding-bottom: 3px; margin: 22px 0 10px; }}
  h3 {{ font-size: 14px; margin: 12px 0 2px; }}
  ul {{ margin: 6px 0 6px 18px; }}
  a {{ color: #1a4f8a; }}
  @media print {{ body {{ margin: 0; }} }}
</style></head><body>
{body}
</body></html>
"""


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "job"


def _markdown_to_html(md: str) -> str:
    """Convert Markdown to HTML, using the `markdown` lib if present."""
    try:
        import markdown  # type: ignore

        return markdown.markdown(md, extensions=["extra"])
    except ImportError:
        # Minimal fallback so a resume still renders without the dependency.
        html = []
        for line in md.splitlines():
            if line.startswith("### "):
                html.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                html.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                html.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("- "):
                html.append(f"<li>{line[2:]}</li>")
            elif line.strip():
                html.append(f"<p>{line}</p>")
        return "\n".join(html)


def render_resume(resume_md: str, company: str, title: str, job_id: int) -> Path:
    """Write the tailored resume to disk and return the HTML file path."""
    out_dir = Path(settings.resolve(settings.resume_output_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_slugify(company)}_{_slugify(title)}_{job_id}"

    (out_dir / f"{stem}.md").write_text(resume_md, encoding="utf-8")
    html = _HTML_TEMPLATE.format(body=_markdown_to_html(resume_md))
    html_path = out_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")

    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html).write_pdf(out_dir / f"{stem}.pdf")
        logger.info("Wrote resume PDF for job {}", job_id)
    except Exception:
        logger.info("PDF renderer not available; HTML written (print to PDF).")

    logger.info("Rendered tailored resume -> {}", html_path)
    return html_path
