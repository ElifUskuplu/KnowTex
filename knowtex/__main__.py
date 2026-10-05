"""``python -m knowtex``: start the local web app (same as ``knowtex serve``).

    python -m knowtex                  # open the page in the browser
    python -m knowtex serve --port N   # options of knowtex.serve
    python -m knowtex notes.md ...     # anything else: the command-line tool
"""

import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] == "serve":
        from knowtex.serve import main as serve_main
        return serve_main(argv[1:] if argv else [])
    from knowtex.cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
