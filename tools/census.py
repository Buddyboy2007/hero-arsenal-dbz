#!/usr/bin/env python3
"""
Census of every character installed in the GMod addon tree.

The tiered roster (extract.py) covers the sixty-six Dragon Ball fighters,
because those are the ones the band system actually governs.  This module
answers the wider question -- what else is installed that you can spawn
and fight -- by reading the entity declarations out of every .gma.

Finding them is a question of what a class INHERITS, not what it is
called.  Two families account for essentially all of them:

  * nextbots -- anything whose Base chain reaches base_nextbot.  DrGBase
    sits one step above that (drgbase_nextbot), and most packs sit above
    DrGBase again through their own pack template, so the chain has to be
    walked rather than matched.
  * VJ Base SNPCs -- anything whose Base chain reaches an npc_vj_*_base.
    These never set ENT.Spawnable: VJ Base registers them into the NPC
    tab itself, so a Spawnable filter would throw the whole family away.

A class is dropped as ABSTRACT when some other class names it as a Base,
or when its own name ends in _base / _template / _base_sv.  That is what
separates "Aizen" from "the Aizen base other Aizens are built on", and it
does it from the install rather than from a hand-written exclusion list
that would rot the next time a pack updates.

Reading is strictly read-only and never touches the model data: the gma
file table is prefix-filtered to lua/entities/ and only those blobs are
pulled, which is what makes a 102 GB tree scannable inside a ten-minute
timer.  Results are cached against each archive's size and mtime, so a
repeat run only re-reads addons that actually changed.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extract import gma_open, gma_read_prefix  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "var", "census-cache.json")

WORKSHOP = os.path.expanduser(
    "~/.local/share/Steam/steamapps/workshop/content/4000")
ADDONS = os.path.expanduser(
    "~/.local/share/Steam/steamapps/common/GarrysMod/garrysmod/addons")

PREFIX = "lua/entities/"

# Pack templates whose children are 2D cut-out nextbots rather than models.
SPRITE_BASE = "drgbase_nextbot_sprite"

ABSTRACT_NAME = re.compile(r"(_base|_template|_base_sv)$")

# FRITAS's engine classes.  haedbz_hero_bot is ONE nextbot class that every
# one of the sixty-six fighters is a configuration of -- it is declared again
# in each of the twelve hero addons, so counting classes here would report
# "Dragon Ball AI" twelve times and the actual fighters zero times.  Those
# fighters come from the roster extractor instead, which reads the hero and
# suit definitions rather than the entity declaration.
ENGINE_CLASSES = {"haedbz_hero_bot", "haedbz_animal"}


# ---------------------------------------------------------------------------
# Reading one archive
# ---------------------------------------------------------------------------

def _str_field(txt, key):
    m = re.search(r"ENT\." + key + r"\s*=\s*([\"'])([^\"']*)\1", txt)
    return m.group(2) if m else None


def _bool_field(txt, key):
    m = re.search(r"ENT\." + key + r"\s*=\s*(true|false)", txt)
    return m.group(1) == "true" if m else None


def _num_field(txt, *keys):
    for key in keys:
        m = re.search(r"ENT\." + key + r"\s*=\s*(\d+)", txt)
        if m:
            return int(m.group(1))
    return None


def scan_archive(path):
    """Every entity class declared in one .gma, or [] if it has none."""
    info = gma_open(path)
    blobs = gma_read_prefix(info, PREFIX)
    if not blobs:
        return []

    # An entity is either lua/entities/<class>.lua or a lua/entities/<class>/
    # directory of init/cl_init/shared -- join a directory's files so a field
    # set in shared.lua is seen alongside one set in init.lua.
    joined = {}
    for inner, data in blobs.items():
        rest = inner[len(PREFIX):]
        head = rest.split("/")[0]
        cls = head[:-4] if head.endswith(".lua") else head
        joined.setdefault(cls, []).append(data)

    rows = []
    for cls, parts in joined.items():
        txt = "\n".join(p.decode("utf8", "ignore") for p in parts)
        rows.append({
            "class": cls,
            "base": _str_field(txt, "Base"),
            "name": _str_field(txt, "PrintName"),
            "category": _str_field(txt, "Category"),
            "spawnable": _bool_field(txt, "Spawnable"),
            "adminOnly": _bool_field(txt, "AdminOnly"),
            "health": _num_field(txt, "MaxHealth", "StartHealth", "Health"),
            "addon": info.get("name") or "",
            "author": info.get("author") or "",
        })
    return rows


# ---------------------------------------------------------------------------
# Walking the whole install, with a cache
# ---------------------------------------------------------------------------

def archives():
    found = []
    for base in (WORKSHOP, ADDONS):
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            full = os.path.join(base, entry)
            if os.path.isfile(full) and entry.endswith(".gma"):
                found.append(("", full))
            elif os.path.isdir(full):
                for name in sorted(os.listdir(full)):
                    if name.endswith(".gma"):
                        wid = entry if base == WORKSHOP else ""
                        found.append((wid, os.path.join(full, name)))
    return found


def load_cache():
    try:
        with open(CACHE) as fh:
            cached = json.load(fh)
    except Exception:
        return {}
    return cached if isinstance(cached, dict) else {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh)
    os.replace(tmp, CACHE)


def declarations():
    """Every entity class in the install, with its archive's identity."""
    cache, fresh, rows = load_cache(), {}, []

    for wid, path in archives():
        try:
            st = os.stat(path)
        except OSError:
            continue

        # mtime alone is a weak fingerprint (a Workshop re-download can land
        # on the same second), so pair it with the size.
        key = path
        stamp = "%d:%d" % (st.st_size, int(st.st_mtime))
        hit = cache.get(key)

        if isinstance(hit, dict) and hit.get("stamp") == stamp:
            found = hit.get("rows") or []
        else:
            try:
                found = scan_archive(path)
            except Exception:
                found = []

        fresh[key] = {"stamp": stamp, "rows": found}

        for row in found:
            row = dict(row)
            row["ws"] = wid
            rows.append(row)

    save_cache(fresh)
    return rows


# ---------------------------------------------------------------------------
# Deciding what is a character
# ---------------------------------------------------------------------------

def _label(cls):
    """A readable name for a class whose pack never declared a PrintName."""
    bare = re.sub(r"^(npc_|drg_|obj_|sent_)", "", cls)
    bare = re.sub(r"^(vj_|drg_|de_|bsr_)+", "", bare)
    return " ".join(w.capitalize() for w in re.split(r"[_\-]+", bare) if w)


def census():
    rows = declarations()

    by_class = {}
    for row in rows:
        by_class.setdefault(row["class"], row)

    bases = {cls: row.get("base") for cls, row in by_class.items()}
    used_as_base = {b for b in bases.values() if b}

    def ancestry(cls):
        seen, out, cur = set(), [], cls
        while True:
            parent = bases.get(cur)
            if not parent or parent in seen:
                if parent:
                    out.append(parent)
                break
            out.append(parent)
            seen.add(parent)
            cur = parent
        return out

    out, seen = [], set()
    for row in rows:
        cls = row["class"]
        line = [row.get("base")] + ancestry(cls)

        if "base_nextbot" in line:
            family = "DrGBase" if "drgbase_nextbot" in line else "Nextbot"
        elif any(re.match(r"^npc_vj_", b or "") for b in line):
            family = "VJ Base"
        else:
            continue

        if cls in used_as_base or ABSTRACT_NAME.search(cls):
            continue

        if cls in ENGINE_CLASSES:
            continue

        # DrGBase itself ships inside more than one installed addon, so a
        # handful of classes are declared twice.  The class name is what the
        # game keys on, so the second declaration is the same character.
        if cls in seen:
            continue
        seen.add(cls)

        out.append({
            "class": cls,
            "name": row.get("name") or _label(cls),
            "named": bool(row.get("name")),
            "family": family,
            "sprite": SPRITE_BASE in line,
            "pack": row.get("addon") or "",
            "ws": row.get("ws") or "",
            "category": row.get("category") or "",
            "health": row.get("health"),
            "adminOnly": bool(row.get("adminOnly")),
        })

    out.sort(key=lambda r: (r["pack"].lower(), r["name"].lower()))
    return out


if __name__ == "__main__":
    import collections
    chars = census()
    print("characters:", len(chars))
    print("packs:", len(set(c["pack"] for c in chars)))
    print(collections.Counter(c["family"] for c in chars))
    print("with health:", sum(1 for c in chars if c["health"]))
