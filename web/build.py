#!/usr/bin/env python3
"""Build the single-file web page (docs/index.html).

The page runs KnowTeX's Python core in the browser with Pyodide.  This
script gathers the Python sources the page needs -- the knowtex core
(core only), a subset of pylatexenc and the English Snowball stemmer --
and inlines them into web/template.html as a JSON bundle.

Usage:
    python web/build.py                 # writes docs/index.html
    python web/build.py --extract DIR   # only unpack the bundle to DIR
                                        # (to test the subset with CPython)
"""

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "web" / "template.html"
OUTPUT = ROOT / "docs" / "index.html"

KNOWTEX_FILES = [
    "knowtex/__init__.py",
    "knowtex/core/__init__.py",
    "knowtex/core/constants.py",
    "knowtex/core/data.py",
    "knowtex/core/utils.py",
    "knowtex/core/parser.py",
    "knowtex/core/structure.py",
    "knowtex/core/file_expand.py",
    "knowtex/core/cycles.py",
    "knowtex/core/dot.py",
    "knowtex/core/formats.py",
    "knowtex/core/text_parser.py",
    "knowtex/deps/__init__.py",
    "knowtex/deps/infer.py",
    "knowtex/deps/term_extraction.py",
    "knowtex/deps/index_registry.py",
    "knowtex/deps/manual.py",
    "knowtex/webapi.py",
]

PYLATEXENC_FILES = [
    "__init__.py",
    "version.py",
    "_util.py",
    "latexwalker/__init__.py",
    "latexwalker/_defaultspecs.py",
    "macrospec/__init__.py",
    "macrospec/_argparsers.py",
]

SNOWBALL_FILES = ["among.py", "basestemmer.py", "english_stemmer.py"]
SNOWBALL_INIT = '''"""English-only subset of snowballstemmer for the browser build."""
from .english_stemmer import EnglishStemmer

__all__ = ("stemmer", "algorithms")


def algorithms():
    return ["english"]


def stemmer(lang):
    if lang.lower() != "english":
        raise KeyError(lang)
    return EnglishStemmer()
'''


def _site_dir(modname):
    mod = importlib.import_module(modname)
    return Path(mod.__file__).resolve().parent


def collect():
    bundle = {}
    for rel in KNOWTEX_FILES:
        bundle[rel] = (ROOT / rel).read_text(encoding="utf-8")
    pl = _site_dir("pylatexenc")
    for rel in PYLATEXENC_FILES:
        bundle[f"pylatexenc/{rel}"] = (pl / rel).read_text(encoding="utf-8")
    sb = _site_dir("snowballstemmer")
    for rel in SNOWBALL_FILES:
        bundle[f"snowballstemmer/{rel}"] = (sb / rel).read_text(encoding="utf-8")
    bundle["snowballstemmer/__init__.py"] = SNOWBALL_INIT
    return bundle


def extract(bundle, target):
    target = Path(target)
    for rel, src in bundle.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src, encoding="utf-8")
    print(f"extracted {len(bundle)} files to {target}")


def build(bundle):
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(bundle, ensure_ascii=False)
    # A JSON script block must not contain "</script>".
    payload = payload.replace("</", "<\\/")
    marker = "/*__PY_BUNDLE__*/"
    if marker not in template:
        sys.exit(f"marker {marker} not found in {TEMPLATE}")
    html = template.replace(marker, payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    size = OUTPUT.stat().st_size
    print(f"wrote {OUTPUT} ({size/1024:.0f} KB, bundle {len(payload)/1024:.0f} KB, "
          f"{len(bundle)} python files)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", metavar="DIR")
    args = ap.parse_args()
    bundle = collect()
    if args.extract:
        extract(bundle, args.extract)
    else:
        build(bundle)


if __name__ == "__main__":
    main()
