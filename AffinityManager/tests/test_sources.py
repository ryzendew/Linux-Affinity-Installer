"""The shipped tree names only public sources and no personal details.

The same commit is tried on a private server, then on a public staging
branch, then published; where it was fetched from is decided by the URL it was
started with (see run.py), never by the code. So nothing in the tree may name
the private server, and nothing may carry a personal address or an AI
co-author line -- the files are published as they are.

Scans the manager and, when it sits inside the installer's repository as
AffinityManager/, that whole repository.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT.parent if (ROOT.parent / "AffinityScripts").is_dir() else ROOT

# Assembled from pieces so this file does not match itself.
FORBIDDEN = {
    "private server": "facemyer" + ".net",
    "work address": "impressus" + "art",
    "AI co-author line": "co-authored-by: " + "claude",
    "AI session link": "claude" + ".ai/code",
    "AI generated-with line": "generated with " + "claude",
    "private development repository": "affinity" + "-linux",
}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules"}


def _text_files():
    for path in CHECKOUT.rglob("*"):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(CHECKOUT).parts):
            continue
        try:
            yield path, path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue


@pytest.mark.parametrize("what", sorted(FORBIDDEN))
def test_nothing_in_the_tree_names_it(what):
    needle = FORBIDDEN[what]
    hits = [str(p.relative_to(CHECKOUT)) for p, text in _text_files() if needle in text]
    assert not hits, f"{what} appears in: {', '.join(sorted(hits))}"


def test_the_scan_actually_reads_the_tree():
    names = {p.name for p, _ in _text_files()}
    assert "run.py" in names and "README.md" in names
