"""Convert .docx files to .pdf using LibreOffice headless."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

PDF_OUTPUT_DIR = "generated_pdfs"

_CANDIDATES = [
    "/usr/bin/libreoffice",
    "/usr/local/bin/libreoffice",
    "/snap/bin/libreoffice",
]


def _find_libreoffice() -> str:
    path = shutil.which("libreoffice")
    if path:
        return path
    for candidate in _CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError(
        "LibreOffice not found. Install with: sudo apt-get install libreoffice"
    )


def convert_docx_to_pdf(
    docx_paths: list[str],
    output_dir: str = PDF_OUTPUT_DIR,
) -> list[str]:
    """Convert a list of .docx files to .pdf in output_dir.

    Returns the paths of successfully created PDF files.
    """
    if not docx_paths:
        return []

    os.makedirs(output_dir, exist_ok=True)
    lo_bin = _find_libreoffice()
    pdf_paths: list[str] = []

    for docx_path in docx_paths:
        docx_path = str(docx_path)
        if not os.path.isfile(docx_path):
            log.warning("DOCX not found, skipping: %s", docx_path)
            continue

        expected_pdf = os.path.join(output_dir, Path(docx_path).stem + ".pdf")

        try:
            result = subprocess.run(
                [
                    lo_bin,
                    "--headless",
                    "--norestore",
                    "--convert-to", "pdf",
                    "--outdir", output_dir,
                    docx_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                log.error(
                    "LibreOffice failed for %s (rc=%d): %s",
                    docx_path, result.returncode, result.stderr.strip(),
                )
                continue

            if os.path.isfile(expected_pdf):
                pdf_paths.append(expected_pdf)
                log.info("Converted: %s → %s", os.path.basename(docx_path), expected_pdf)
            else:
                log.error("PDF not found after conversion: %s", expected_pdf)

        except subprocess.TimeoutExpired:
            log.error("LibreOffice timed out: %s", docx_path)
        except Exception as e:
            log.error("Error converting %s: %s", docx_path, e, exc_info=True)

    log.info("pdf_converter: %d/%d converted", len(pdf_paths), len(docx_paths))
    return pdf_paths
