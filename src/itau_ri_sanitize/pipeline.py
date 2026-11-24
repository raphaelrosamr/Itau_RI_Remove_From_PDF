from __future__ import annotations

import json
import shutil
from pathlib import Path

from itau_ri_sanitize.classify import (
    KEEP,
    REMOVE,
    REVIEW,
    PageDecision,
    classify_text,
    expand_neighbors,
    pages_sharing_report_logo,
)
from itau_ri_sanitize.db import connect
from itau_ri_sanitize.families import family_from_filename, family_from_text
from itau_ri_sanitize.lexicon import fold, get_lexicon
from itau_ri_sanitize.paths import pipeline_dir, raw_dir
from itau_ri_sanitize.pdfio import (
    export_single_pages,
    iter_pdfs,
    read_pdf,
    render_pages,
    sha256_file,
    write_without_pages,
)


def _relative_source(path: Path) -> Path:
    try:
        return path.resolve().relative_to(raw_dir().resolve())
    except ValueError:
        return Path(path.name)


def decide_document(parsed: dict, family: str) -> list[PageDecision]:
    lexicon = get_lexicon()
    texts = [page["text"] for page in parsed["pages"]]
    n_pages = len(texts)
    decisions = [
        classify_text(
            page["text"],
            page_index=page["page_index"],
            n_pages=n_pages,
            family=family,
            n_chars=page["n_chars"],
            lexicon=lexicon,
        )
        for page in parsed["pages"]
    ]
    small_image = [bool(page["small_image_xrefs"]) for page in parsed["pages"]]
    decisions = expand_neighbors(decisions, texts, small_image, lexicon)
    xrefs = {page["page_index"]: set(page["small_image_xrefs"]) for page in parsed["pages"]}
    remove_at = {d.page_index for d in decisions if d.action == REMOVE}
    for index in pages_sharing_report_logo(xrefs, remove_at):
        decisions[index] = decisions[index].with_reason(REMOVE, "logo")
    return decisions


def _counts(decisions: list[PageDecision]) -> dict[str, int]:
    return {
        REMOVE: sum(d.action == REMOVE for d in decisions),
        REVIEW: sum(d.action == REVIEW for d in decisions),
        KEEP: sum(d.action == KEEP for d in decisions),
    }


def process_file(path: Path, *, render: bool = False, force: bool = False) -> dict:
    conn = connect()
    try:
        return _process_file(conn, path, render=render, force=force)
    finally:
        conn.close()


def _process_file(conn, path: Path, *, render: bool, force: bool) -> dict:
    path = path.resolve()
    digest = sha256_file(path)
    conn.execute(
        "INSERT INTO paths(path, sha256) VALUES(?, ?) ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256",
        (str(path), digest),
    )
    already = conn.execute("SELECT status, staging_path FROM documents WHERE sha256=?", (digest,)).fetchone()
    if already and not force and already["status"] in {"pronto", "revisao", "excluido"}:
        conn.commit()
        return {
            "sha256": digest,
            "path": str(path),
            "status": already["status"],
            "skipped": True,
            "staging_path": already["staging_path"],
        }

    parsed = read_pdf(path)
    if parsed is None or parsed.get("error"):
        error = (parsed or {}).get("error", "ilegivel")
        status = "quarentena" if error == "criptografado" else "falhou"
        conn.execute(
            """
            INSERT INTO documents(sha256, size_bytes, n_pages, family, status, error)
            VALUES(?, ?, NULL, NULL, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET status=excluded.status, error=excluded.error
            """,
            (digest, path.stat().st_size, status, error),
        )
        conn.commit()
        return {"sha256": digest, "path": str(path), "status": status, "error": error}

    filename_family = family_from_filename(path.name)
    head = "\n".join(fold(page["text"])[:1500] for page in parsed["pages"][:3])
    family = family_from_text(head, filename_family)
    decisions = decide_document(parsed, family)
    counts = _counts(decisions)
    remove_indexes = [d.page_index for d in decisions if d.action == REMOVE]

    rel = _relative_source(path)
    staging_path = None
    if remove_indexes and len(remove_indexes) < parsed["n_pages"]:
        staging_path = pipeline_dir() / "staging" / rel
        write_without_pages(path, staging_path, remove_indexes)
        export_single_pages(
            path,
            pipeline_dir() / "removed" / digest[:16],
            remove_indexes,
        )
    elif not remove_indexes:
        staging_path = path

    if counts[REVIEW]:
        status = "revisao"
    elif len(remove_indexes) == parsed["n_pages"]:
        status = "excluido"
        staging_path = None
    else:
        status = "pronto"

    conn.execute(
        """
        INSERT INTO documents(sha256, size_bytes, n_pages, family, status, error, staging_path, n_remove, n_review, n_keep)
        VALUES(?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
        ON CONFLICT(sha256) DO UPDATE SET
            n_pages=excluded.n_pages,
            family=excluded.family,
            status=excluded.status,
            error=NULL,
            staging_path=excluded.staging_path,
            n_remove=excluded.n_remove,
            n_review=excluded.n_review,
            n_keep=excluded.n_keep
        """,
        (
            digest,
            path.stat().st_size,
            parsed["n_pages"],
            family,
            status,
            str(staging_path) if staging_path else None,
            counts[REMOVE],
            counts[REVIEW],
            counts[KEEP],
        ),
    )
    conn.execute("DELETE FROM pages WHERE sha256=?", (digest,))
    conn.executemany(
        "INSERT INTO pages(sha256, page_index, n_chars, action, reasons) VALUES(?, ?, ?, ?, ?)",
        [
            (
                digest,
                d.page_index,
                parsed["pages"][d.page_index]["n_chars"],
                d.action,
                json.dumps(list(d.reasons), ensure_ascii=False),
            )
            for d in decisions
        ],
    )
    conn.commit()

    review_dir = None
    if render:
        watched = [d.page_index for d in decisions if d.action in {REMOVE, REVIEW}]
        if watched:
            review_dir = pipeline_dir() / "work" / "review" / digest[:16]
            render_pages(path, review_dir, watched)
            _write_review_html(review_dir, path, decisions, parsed["n_pages"], family)

    return {
        "sha256": digest,
        "path": str(path),
        "family": family,
        "status": status,
        "n_pages": parsed["n_pages"],
        "n_remove": counts[REMOVE],
        "n_review": counts[REVIEW],
        "n_keep": counts[KEEP],
        "remove_pages": [i + 1 for i in remove_indexes],
        "staging_path": str(staging_path) if staging_path else None,
        "review_dir": str(review_dir) if review_dir else None,
        "skipped": False,
    }


def _write_review_html(dest: Path, source: Path, decisions: list[PageDecision], n_pages: int, family: str) -> None:
    rows = []
    for decision in decisions:
        if decision.action == KEEP:
            continue
        img = f"p{decision.page_index + 1:04d}.jpg"
        rows.append(
            "<tr>"
            f"<td>{decision.page_index + 1}</td>"
            f"<td>{decision.action}</td>"
            f"<td>{', '.join(decision.reasons)}</td>"
            f"<td><img src='{img}' alt='pagina {decision.page_index + 1}'></td>"
            "</tr>"
        )
    html = (
        "<!DOCTYPE html><meta charset='utf-8'><title>Revisão</title>"
        "<style>img{max-width:420px;border:1px solid #ccc}td{vertical-align:top;padding:8px}</style>"
        f"<h1>{source.name}</h1><p>{family} · {n_pages} páginas</p>"
        "<table>" + "".join(rows) + "</table>"
    )
    (dest / "index.html").write_text(html, encoding="utf-8")


def release_ready() -> list[Path]:
    """Copia para a entrega só o que não tem página em revisão."""
    conn = connect()
    delivered = []
    try:
        rows = conn.execute(
            "SELECT sha256, staging_path, status, n_remove FROM documents WHERE status='pronto' AND staging_path IS NOT NULL"
        ).fetchall()
        out_root = pipeline_dir() / "deliverable"
        for row in rows:
            source = Path(row["staging_path"])
            if not source.exists():
                continue
            paths = conn.execute("SELECT path FROM paths WHERE sha256=?", (row["sha256"],)).fetchall()
            for item in paths:
                rel = _relative_source(Path(item["path"]))
                dest = out_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() == Path(item["path"]).resolve():
                    shutil.copy2(source, dest)
                else:
                    shutil.copy2(source, dest)
                delivered.append(dest)
        manifest = pipeline_dir() / "deliverable" / "manifest.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", encoding="utf-8") as handle:
            for row in conn.execute(
                """
                SELECT d.sha256, d.family, d.status, d.n_pages, d.n_remove, d.n_review, d.staging_path, p.path
                FROM documents d JOIN paths p ON p.sha256 = d.sha256
                WHERE d.status IN ('pronto', 'excluido', 'revisao')
                """
            ):
                pages = conn.execute(
                    "SELECT page_index, action, reasons FROM pages WHERE sha256=? AND action!='keep' ORDER BY page_index",
                    (row["sha256"],),
                ).fetchall()
                handle.write(
                    json.dumps(
                        {
                            "sha256": row["sha256"],
                            "source": row["path"],
                            "family": row["family"],
                            "status": row["status"],
                            "n_pages": row["n_pages"],
                            "n_remove": row["n_remove"],
                            "n_review": row["n_review"],
                            "pages": [
                                {
                                    "page": item["page_index"] + 1,
                                    "action": item["action"],
                                    "reasons": json.loads(item["reasons"]),
                                }
                                for item in pages
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    finally:
        conn.close()
    return delivered


def qa_pdf(path: Path) -> list[dict]:
    """Relê um PDF de saída e devolve páginas que ainda têm detector de peça."""
    parsed = read_pdf(path)
    if not parsed or parsed.get("error"):
        return [{"page": None, "error": (parsed or {}).get("error", "ilegivel")}]
    hits = []
    for page in parsed["pages"]:
        decision = classify_text(
            page["text"],
            page_index=page["page_index"],
            n_pages=parsed["n_pages"],
            family="outros",
            n_chars=page["n_chars"],
        )
        if decision.action == REMOVE:
            hits.append(
                {
                    "page": page["page_index"] + 1,
                    "reasons": list(decision.reasons),
                }
            )
    return hits


def iter_source_pdfs() -> list[Path]:
    return list(iter_pdfs(raw_dir()))
