"""Executable public example: installed package + supplied JSON responses, zero API calls.

Run from a source checkout or sdist with an installed wheel. The response file is
hand-authored and fixed; this exercises the provider protocol, not model autonomy.
"""
from investigator.cli import main


if __name__ == "__main__":
    import sys
    raise SystemExit(main(["investigate", *sys.argv[1:]]))
