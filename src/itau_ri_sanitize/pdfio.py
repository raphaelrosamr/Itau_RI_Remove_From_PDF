from __future__ import annotations

import hashlib
from pathlib import Path

import pikepdf
import pymupdf

from itau_ri_sanitize.lexicon import fold


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_pdfs(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() == ".pdf" or path.name.lower().endswith(".pdf.pdf"):
            yield path


def _small_image_xrefs(page: pymupdf.Page) -> set[int]:
    found: set[int] = set()
    try:
        info = page.get_image_info()
    except Exception:
        return found
    for item in info:
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        xref = int(item.get("xref") or 0)
        if xref <= 0:
            continue
        longest = max(width, height)
        shortest = min(width, height)
        if 15 <= shortest and longest <= 700:
            found.add(xref)
    return found


def read_pdf(path: Path) -> dict | None:
    """Lê texto e imagens pequenas. None se o PDF não abrir."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    if doc.is_encrypted:
        if not doc.authenticate(""):
            doc.close()
            return {"error": "criptografado"}
    pages = []
    try:
        for index, page in enumerate(doc):
            try:
                text = page.get_text("text") or ""
            except Exception:
                text = ""
            xrefs = _small_image_xrefs(page)
            pages.append(
                {
                    "page_index": index,
                    "text": text,
                    "n_chars": len(fold(text).strip()),
                    "small_image_xrefs": xrefs,
                }
            )
    finally:
        doc.close()
    return {"n_pages": len(pages), "pages": pages}


def write_without_pages(source: Path, dest: Path, remove_indexes: list[int]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with pikepdf.open(source) as pdf:
        for index in sorted(remove_indexes, reverse=True):
            del pdf.pages[index]
        if "/Outlines" in pdf.Root:
            del pdf.Root["/Outlines"]
        pdf.save(dest, linearize=True)


def export_single_pages(source: Path, dest_dir: Path, indexes: list[int]) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with pikepdf.open(source) as pdf:
        for index in indexes:
            single = pikepdf.Pdf.new()
            single.pages.append(pdf.pages[index])
            single.save(dest_dir / f"p{index + 1:04d}.pdf")


def render_pages(source: Path, dest_dir: Path, indexes: list[int], dpi: int = 72) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    doc = pymupdf.open(source)
    try:
        for index in indexes:
            if index < 0 or index >= doc.page_count:
                continue
            target = dest_dir / f"p{index + 1:04d}.jpg"
            pix = doc[index].get_pixmap(dpi=dpi)
            pix.save(target)
            written.append(target)
    finally:
        doc.close()
    return written
