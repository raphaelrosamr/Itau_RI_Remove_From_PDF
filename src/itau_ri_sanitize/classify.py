from __future__ import annotations

import re
from dataclasses import dataclass

from itau_ri_sanitize.lexicon import Lexicon, fold, get_lexicon


REMOVE = "remove"
KEEP = "keep"
REVIEW = "review"


@dataclass(frozen=True)
class PageDecision:
    page_index: int
    action: str
    reasons: tuple[str, ...]

    def with_reason(self, action: str, reason: str) -> PageDecision:
        if reason in self.reasons and action == self.action:
            return self
        return PageDecision(self.page_index, action, self.reasons + (reason,))


def _search_any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _title_kinds(text: str, lexicon: Lexicon) -> tuple[bool, bool]:
    """Retorna (titulo_de_peca, titulo_so_no_sumario)."""
    heading = False
    toc = False
    for line in text.splitlines():
        if not any(p.search(line) for p in lexicon.titles):
            continue
        compact = " ".join(line.split())
        is_toc = len(compact) < 160 and (
            "...." in compact or re.search(r"(?:\s|\.)\d{1,4}\s*$", compact) is not None
        )
        if is_toc:
            toc = True
        else:
            heading = True
    if not heading and not toc:
        # Título partido em mais de uma linha.
        flat = " ".join(text.split())
        if any(p.search(flat) for p in lexicon.titles):
            heading = True
    return heading, toc


def _harmless_hits(text: str, lexicon: Lexicon) -> list[str]:
    hits = []
    for name, patterns in lexicon.harmless.items():
        if _search_any(patterns, text):
            hits.append(name)
    return hits


def _is_cadastro(hits: list[str]) -> bool:
    return "cadastro_firma" in hits


def classify_text(
    text: str,
    *,
    page_index: int,
    n_pages: int,
    family: str,
    n_chars: int | None = None,
    lexicon: Lexicon | None = None,
) -> PageDecision:
    lexicon = lexicon or get_lexicon()
    folded = fold(text)
    chars = len(folded.strip()) if n_chars is None else n_chars
    heading, toc_only = _title_kinds(folded, lexicon)
    verb = _search_any(lexicon.verbs, folded)
    crc = lexicon.crc.search(folded) is not None
    addressee = _search_any(lexicon.addressees, folded)
    firm = _search_any(lexicon.firms, folded)
    auditor_mention = "auditor independente" in folded or "independent auditor" in folded
    harmless = _harmless_hits(folded, lexicon)
    cadastro = _is_cadastro(harmless)

    reasons: list[str] = []
    # Título de sumário não é a peça. Título de seção, verbo ou CRC são.
    if heading or verb or addressee or (crc and not cadastro):
        if heading:
            reasons.append("titulo")
        if verb:
            reasons.append("verbo_opiniao")
        if addressee and (heading or verb or crc):
            reasons.append("destinatario")
        if crc and not cadastro:
            reasons.append("crc")
        if reasons:
            return PageDecision(page_index, REMOVE, tuple(reasons))

    if toc_only:
        harmless.append("sumario")

    in_risk = family in (
        lexicon.risk_families_first
        | lexicon.risk_families_last
        | lexicon.risk_families_low_text
    )
    edge = lexicon.risk_edge_pages
    in_first = family in lexicon.risk_families_first and page_index < edge
    in_last = family in lexicon.risk_families_last and page_index >= max(0, n_pages - edge)
    low_text = chars < lexicon.low_text_chars and family in lexicon.risk_families_low_text

    if harmless:
        if in_risk and not lexicon.trust_harmless_in_risk_docs:
            return PageDecision(page_index, REVIEW, tuple(harmless) + ("revisao_mencao_em_doc_de_risco",))
        return PageDecision(page_index, KEEP, tuple(harmless))

    zone_reasons: list[str] = []
    if firm or auditor_mention:
        zone_reasons.append("mencao_firma" if firm else "mencao_auditor")
    if in_first:
        zone_reasons.append("zona_inicio")
    if in_last:
        zone_reasons.append("zona_fim")
    if low_text:
        zone_reasons.append("pouco_texto")
    if zone_reasons:
        return PageDecision(page_index, REVIEW, tuple(zone_reasons))
    return PageDecision(page_index, KEEP, ("sem_sinal",))


def expand_neighbors(
    decisions: list[PageDecision],
    texts: list[str],
    small_image: list[bool],
    lexicon: Lexicon | None = None,
) -> list[PageDecision]:
    """Página ao lado de um parecer sai se for continuação, CRC ou página de assinatura."""
    lexicon = lexicon or get_lexicon()
    remove_at = {d.page_index for d in decisions if d.action == REMOVE}
    if not remove_at:
        return decisions
    updated = list(decisions)
    for decision in decisions:
        if decision.action == REMOVE:
            continue
        near = any(0 < abs(decision.page_index - other) <= 2 for other in remove_at)
        if not near:
            continue
        folded = fold(texts[decision.page_index])
        continuation = "continuacao" in folded and (
            "relatorio do auditor" in folded
            or "relatorio dos auditores" in folded
            or "independent auditor" in folded
            or lexicon.crc.search(folded) is not None
        )
        signature_page = small_image[decision.page_index] and len(folded.strip()) < lexicon.low_text_chars
        if continuation or signature_page:
            updated[decision.page_index] = decision.with_reason(REMOVE, "vizinha_da_peca")
    return updated


def pages_sharing_report_logo(
    image_xrefs_by_page: dict[int, set[int]],
    remove_pages: set[int],
) -> set[int]:
    """XObject pequeno que está na peça e em no máximo duas outras páginas.

    Imagem que se repete no documento inteiro (logo do Itaú, masthead) fica de fora.
    """
    if not remove_pages:
        return set()
    pages_of: dict[int, set[int]] = {}
    for page_index, xrefs in image_xrefs_by_page.items():
        for xref in xrefs:
            pages_of.setdefault(xref, set()).add(page_index)
    extra: set[int] = set()
    for pages in pages_of.values():
        if not (pages & remove_pages):
            continue
        outside = pages - remove_pages
        if not outside or len(outside) > 2:
            continue
        extra |= outside
    return extra
