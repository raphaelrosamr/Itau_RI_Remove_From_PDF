from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from itau_ri_sanitize.paths import lexicon_path


def fold(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.casefold()


@dataclass(frozen=True)
class Lexicon:
    low_text_chars: int
    risk_edge_pages: int
    trust_harmless_in_risk_docs: bool
    risk_families_first: frozenset[str]
    risk_families_last: frozenset[str]
    risk_families_low_text: frozenset[str]
    titles: tuple[re.Pattern[str], ...]
    verbs: tuple[re.Pattern[str], ...]
    crc: re.Pattern[str]
    addressees: tuple[re.Pattern[str], ...]
    firms: tuple[re.Pattern[str], ...]
    harmless: dict[str, tuple[re.Pattern[str], ...]]


def _compile_many(patterns: list[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


def load_lexicon(path: Path | None = None) -> Lexicon:
    raw = yaml.safe_load((path or lexicon_path()).read_text(encoding="utf-8"))
    harmless = {
        name: _compile_many(patterns) for name, patterns in raw["harmless"].items()
    }
    return Lexicon(
        low_text_chars=int(raw["low_text_chars"]),
        risk_edge_pages=int(raw["risk_edge_pages"]),
        trust_harmless_in_risk_docs=bool(raw["trust_harmless_in_risk_docs"]),
        risk_families_first=frozenset(raw["risk_families_first"]),
        risk_families_last=frozenset(raw["risk_families_last"]),
        risk_families_low_text=frozenset(raw["risk_families_low_text"]),
        titles=_compile_many(raw["titles"]),
        verbs=_compile_many(raw["verbs"]),
        crc=re.compile(raw["crc"], re.IGNORECASE),
        addressees=_compile_many(raw["addressees"]),
        firms=_compile_many(raw["firms"]),
        harmless=harmless,
    )


@lru_cache(maxsize=1)
def get_lexicon() -> Lexicon:
    return load_lexicon()
