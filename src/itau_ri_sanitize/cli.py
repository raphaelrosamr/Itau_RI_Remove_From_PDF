from __future__ import annotations

import argparse
import sys

from itau_ri_sanitize.paths import raw_dir
from itau_ri_sanitize.pdfio import iter_pdfs
from itau_ri_sanitize.pipeline import process_file, qa_pdf, release_ready


def _cmd_process(args: argparse.Namespace) -> int:
    if args.path:
        targets = [args.path]
    else:
        targets = list(iter_pdfs(raw_dir()))
        if args.limit:
            targets = targets[: args.limit]
    failures = 0
    for path in targets:
        result = process_file(path, render=args.render, force=args.force)
        if result.get("skipped"):
            print(f"ja processado  {result['status']}  {path.name}")
            continue
        if result.get("error"):
            failures += 1
            print(f"erro  {result['status']}  {result['error']}  {path.name}")
            continue
        pages = ",".join(str(n) for n in result["remove_pages"]) or "-"
        print(
            f"{result['status']:10}  remove={result['n_remove']:3}  "
            f"revisao={result['n_review']:3}  fica={result['n_keep']:3}  "
            f"paginas={pages}  {result['family']:22}  {path.name}"
        )
    return 1 if failures else 0


def _cmd_qa(args: argparse.Namespace) -> int:
    hits = qa_pdf(args.path)
    if not hits:
        print("nenhum detector de peça restante")
        return 0
    for hit in hits:
        print(hit)
    return 1


def _cmd_release(_args: argparse.Namespace) -> int:
    delivered = release_ready()
    print(f"entregues: {len(delivered)}")
    for path in delivered:
        print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Separa páginas de auditoria externa dos PDFs de RI. Originais em ITAU/ não são alterados."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    process = sub.add_parser("process", help="Classifica PDFs e grava a versão sem as páginas de peça")
    process.add_argument("--path", type=__import__("pathlib").Path, help="Um PDF, em vez do acervo inteiro")
    process.add_argument("--limit", type=int, help="Processa só os N primeiros PDFs do acervo")
    process.add_argument("--render", action="store_true", help="Gera miniatura das páginas removidas e em revisão")
    process.add_argument("--force", action="store_true", help="Reprocessa mesmo que o arquivo já esteja no manifesto")
    process.set_defaults(func=_cmd_process)

    qa = sub.add_parser("qa", help="Relê um PDF e aponta página que ainda tem peça de auditoria")
    qa.add_argument("path", type=__import__("pathlib").Path)
    qa.set_defaults(func=_cmd_qa)

    release = sub.add_parser("release", help="Copia para pipeline/deliverable só arquivos sem página em revisão")
    release.set_defaults(func=_cmd_release)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
