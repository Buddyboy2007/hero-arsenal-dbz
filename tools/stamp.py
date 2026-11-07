#!/usr/bin/env python3
"""
Hold data.json's timestamp still when nothing else changed.

extract.py stamps every run with the current time, so a plain diff would
report a change every ten minutes forever and the repo would fill with empty
commits. This compares the fresh data.json against the one already committed,
ignoring that timestamp alone -- and if they match, puts the old timestamp
back. The build then regenerates byte-identical pages, git sees a clean tree,
and update.sh has a single honest test for "did anything actually change".
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data.json")
KEY = "generatedAt"


def committed():
    try:
        out = subprocess.run(["git", "-C", ROOT, "show", "HEAD:data.json"],
                             capture_output=True, check=True).stdout
        return json.loads(out)
    except Exception:
        return None


def main():
    old = committed()
    if old is None:
        print("stamp: no committed data.json yet")
        return
    new = json.load(open(PATH))
    a, b = dict(old), dict(new)
    a.pop(KEY, None)
    b.pop(KEY, None)
    if a != b:
        print("stamp: roster changed, keeping the new timestamp")
        return
    new[KEY] = old.get(KEY, new.get(KEY))
    with open(PATH, "w") as fh:
        json.dump(new, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print("stamp: roster unchanged, timestamp held at " + str(new[KEY]))


if __name__ == "__main__":
    main()
