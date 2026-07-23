"""One-off script that generates tests/fixtures/sample.pdf.

Not run as part of the test suite or the app — it's a generator, not a test.
Requires `reportlab`, which is a dev-only dependency (see requirements-dev.txt)
used solely to produce this fixture; the app itself never creates PDFs, only
reads them (via pypdf), so reportlab is not a runtime dependency.

Re-run with: python tests/fixtures/generate_pdf_fixture.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

OUT_PATH = Path(__file__).resolve().parent / "sample.pdf"

PAGE_1_LINES = [
    "Process Scheduling",
    "",
    "Process scheduling is the activity of the operating system that",
    "decides which process runs on the CPU at any given time.",
    "Common algorithms include First-Come First-Served, Shortest Job",
    "First, Round Robin, and Priority Scheduling.",
]

PAGE_2_LINES = [
    "Deadlocks",
    "",
    "A deadlock occurs when a set of processes are each waiting for a",
    "resource held by another process in the set, so none of them can",
    "proceed. The four necessary conditions are mutual exclusion, hold",
    "and wait, no preemption, and circular wait.",
]


def _write_page(c: canvas.Canvas, lines: list[str]) -> None:
    text = c.beginText(72, 720)
    text.setFont("Helvetica", 12)
    for line in lines:
        text.textLine(line)
    c.drawText(text)
    c.showPage()


def main() -> None:
    c = canvas.Canvas(str(OUT_PATH), pagesize=LETTER)
    _write_page(c, PAGE_1_LINES)
    _write_page(c, PAGE_2_LINES)
    c.save()
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
