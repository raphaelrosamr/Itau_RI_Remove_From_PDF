import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("ITAU_RI_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def raw_dir() -> Path:
    env = os.environ.get("ITAU_RI_RAW")
    if env:
        return Path(env)
    return repo_root() / "raw" / "ITAU"


def pipeline_dir() -> Path:
    return repo_root() / "pipeline"


def lexicon_path() -> Path:
    return repo_root() / "config" / "lexicon.yml"
