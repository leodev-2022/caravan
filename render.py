#!/usr/bin/env python3
"""Minimal template renderer (stdlib only).

Usage:
    render.py TEMPLATE OUTPUT (KEY=VALUE | @FILE) ...

Replaces every ``__KEY__`` occurrence with its value. Later sources override
earlier ones. ``@FILE`` reads literal ``KEY=VALUE`` lines (no shell expansion,
so bcrypt hashes containing ``$`` survive). Fails closed if any placeholder is
left unresolved.
"""
import re
import sys


def parse_file(path, into):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            into[key.strip()] = val.strip()


def main(argv):
    if len(argv) < 3:
        sys.exit("usage: render.py TEMPLATE OUTPUT (KEY=VALUE | @FILE) ...")
    tmpl, out, args = argv[1], argv[2], argv[3:]
    variables = {}
    for arg in args:
        if arg.startswith("@"):
            parse_file(arg[1:], variables)
        elif "=" in arg:
            key, val = arg.split("=", 1)
            variables[key] = val
        else:
            sys.exit(f"bad argument (expected KEY=VALUE or @FILE): {arg}")
    with open(tmpl, encoding="utf-8") as fh:
        text = fh.read()
    for key, val in variables.items():
        text = text.replace(f"__{key}__", val)
    leftover = sorted(set(re.findall(r"__[A-Z0-9_]+__", text)))
    if leftover:
        sys.exit("unresolved placeholders: " + ", ".join(leftover))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"rendered {out}")


if __name__ == "__main__":
    main(sys.argv)
