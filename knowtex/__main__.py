"""Allow running as: python -m knowtex"""

from knowtex.gui.app import KnowTex

if __name__ == "__main__":
    app = KnowTex()
    app.mainloop()
