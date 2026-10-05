#!/usr/bin/env python3
"""Start KnowTeX: the web page served locally, opened in your browser.

Usage:
    python KnowTeX.py
    python -m knowtex serve --port 8765
"""

import sys

from knowtex.serve import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
