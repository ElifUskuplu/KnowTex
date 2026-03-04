#!/usr/bin/env python3
"""Entry point for the unified KnowTeX application.

Usage:
    python KnowTeX.py
    python -m knowtex
"""

from knowtex.gui.app import KnowTex


def main():
    app = KnowTex()
    app.mainloop()


if __name__ == "__main__":
    main()
