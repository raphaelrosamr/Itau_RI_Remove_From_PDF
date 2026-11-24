from __future__ import annotations

import re


_FILENAME_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("conselho_fiscal", re.compile(r"conselho_fiscal", re.I)),
    ("formulario_referencia", re.compile(r"formulario_de_referencia|reference_form|formulario_referencia|\bfre_", re.I)),
    ("form_20f", re.compile(r"form_20|20-f|20f", re.I)),
    ("esg", re.compile(r"\besg\b|sustentab|relatorio_integrado|integrated", re.I)),
    ("anual", re.compile(r"relatorio_anual|annual_report|consolidated_annual", re.I)),
    ("analise_gerencial", re.compile(r"analise_gerencial|management_discussion", re.I)),
    ("demonstracoes", re.compile(r"demonstrac|financial_statement|\bdfp\b|\bifrs\b", re.I)),
    ("ata", re.compile(r"\bata_|_ata_|minutes|assembleia", re.I)),
    ("fato_relevante", re.compile(r"fato_relevante|material_fact", re.I)),
    ("politica", re.compile(r"politic|policy", re.I)),
    ("apresentacao", re.compile(r"apresenta|apimec|convite", re.I)),
)


_TEXT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("formulario_referencia", re.compile(r"formulario\s+de\s+referencia|reference\s+form", re.I)),
    ("form_20f", re.compile(r"form\s+20-?f", re.I)),
    ("esg", re.compile(r"relatorio\s+esg|esg\s+report", re.I)),
    ("demonstracoes", re.compile(r"demonstracoes\s+financeiras|complete\s+financial\s+statements|demonstracoes\s+contabeis", re.I)),
)


def slug_from_filename(name: str) -> str:
    stem = name
    lower = stem.lower()
    if lower.endswith(".pdf.pdf"):
        stem = stem[:-4]
        lower = stem.lower()
    if lower.endswith(".pdf"):
        stem = stem[:-4]
    if len(stem) >= 65 and stem[64] == "_" and all(c in "0123456789abcdefABCDEF" for c in stem[:64]):
        return stem[65:]
    head, sep, tail = stem.partition("_")
    if sep and len(head) >= 32 and "-" in head:
        return tail
    return stem


def family_from_filename(name: str) -> str:
    slug = slug_from_filename(name)
    for family, pattern in _FILENAME_RULES:
        if pattern.search(slug):
            return family
    return "outros"


def family_from_text(folded_first_pages: str, filename_family: str) -> str:
    if filename_family != "outros":
        return filename_family
    for family, pattern in _TEXT_RULES:
        if pattern.search(folded_first_pages):
            return family
    return filename_family
