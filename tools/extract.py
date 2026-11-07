#!/usr/bin/env python3
"""Build data.json out of the live GMod install.

Nothing here is typed by hand that the game could be asked for instead. The
roster comes out of z_dbz_bt3.lua by running it (tools/dump_bt3.lua); the
abilities and stats come out of FRITAS's twelve workshop .gma files, whose
hero definitions are JSON already. So a band edited in Lua or a new model
added to the roster shows up on the site at the next build, and there is no
second copy of the roster in this repo to go stale.
"""

import glob, json, os, re, struct, subprocess, sys, time
from datetime import datetime, timezone

HERE    = os.path.dirname(os.path.abspath(__file__))
ROOT    = os.path.dirname(HERE)
GMOD    = os.path.expanduser("~/.local/share/Steam/steamapps/common/GarrysMod/garrysmod")
AUTORUN = os.path.join(GMOD, "lua/autorun")
WORKSHOP= os.path.expanduser("~/.local/share/Steam/steamapps/workshop/content/4000")

# The twelve Hero Arsenal DBZ workshop items. Discovered by scanning, but
# pinned here so a build never silently picks up a different pack -- and so a
# missing one is a reported error rather than a fighter that quietly vanishes.
FRITAS_IDS = [
    "3826583588", "3826830684", "3827243521", "3827477706",
    "3827557962", "3827771848", "3828228243", "3828272973",
    "3828527717", "3829325488", "3830932645", "3831270279",
]

# ---------------------------------------------------------------------------
# .gma reading
# ---------------------------------------------------------------------------

def _cstr(f):
    b = bytearray()
    while True:
        c = f.read(1)
        if not c or c == b"\0":
            break
        b += c
    return b.decode("utf-8", "replace")


def gma_open(path):
    f = open(path, "rb")
    if f.read(4) != b"GMAD":
        f.close()
        return None
    ver = f.read(1)
    f.read(16)                       # steamid + timestamp
    if ver[0] > 1:
        while _cstr(f):
            pass
    name, desc, author = _cstr(f), _cstr(f), _cstr(f)
    f.read(4)
    files = []
    while True:
        if struct.unpack("<I", f.read(4))[0] == 0:
            break
        fn = _cstr(f)
        sz = struct.unpack("<q", f.read(8))[0]
        f.read(4)
        files.append((fn, sz))
    return {"f": f, "files": files, "base": f.tell(),
            "name": name, "desc": desc, "author": author}


def gma_read_prefix(info, prefix):
    """Pull every member under `prefix` without reading the 200MB of models."""
    out, off, f = {}, info["base"], info["f"]
    for fn, sz in info["files"]:
        if fn.startswith(prefix):
            f.seek(off)
            out[fn] = f.read(sz)
        off += sz
    return out


# ---------------------------------------------------------------------------
# FRITAS heroes
# ---------------------------------------------------------------------------

HERO_JSON = re.compile(r"RegisterHeroJSON\(\[=\[(.*?)\]=\]\)", re.S)


def load_fritas(errors):
    heroes = {}
    for wid in FRITAS_IDS:
        hits = glob.glob(os.path.join(WORKSHOP, wid, "*.gma"))
        if not hits:
            errors.append(f"workshop item {wid} has no .gma -- is it still subscribed?")
            continue
        info = gma_open(hits[0])
        if not info:
            errors.append(f"workshop item {wid}: not a .gma")
            continue
        try:
            got = gma_read_prefix(info, "lua/hero_arsenal_dbz/heroes/")
            if not got:
                errors.append(f"workshop item {wid} ({info['name']}): no hero definition inside")
                continue
            for fn, raw in got.items():
                m = HERO_JSON.search(raw.decode("utf-8", "replace"))
                if not m:
                    errors.append(f"{fn}: no RegisterHeroJSON block")
                    continue
                try:
                    hero = json.loads(m.group(1))
                except json.JSONDecodeError as e:
                    errors.append(f"{fn}: hero JSON did not parse ({e})")
                    continue
                hero["_workshop"] = wid
                hero["_packName"] = info["name"]
                heroes[hero["id"]] = hero
        finally:
            info["f"].close()
    return heroes


# ---------------------------------------------------------------------------
# The BT3 roster, by running the real Lua
# ---------------------------------------------------------------------------

def load_bt3(errors):
    lua = None
    for cand in ("luajit", "lua5.1", "lua"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            lua = cand
            break
    if not lua:
        errors.append("no lua interpreter found -- BT3 roster unavailable")
        return {}
    try:
        out = subprocess.run([lua, os.path.join(HERE, "dump_bt3.lua"), AUTORUN],
                             capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        errors.append("dump_bt3.lua timed out")
        return {}
    if out.returncode != 0:
        errors.append(f"dump_bt3.lua failed: {out.stderr.strip()[:300]}")
        return {}
    try:
        d = json.loads(out.stdout)
    except json.JSONDecodeError as e:
        errors.append(f"dump_bt3.lua emitted bad JSON: {e}")
        return {}
    for key in ("bt3Error", "aiError"):
        if d.get(key):
            errors.append(f"{key}: {str(d[key])[:200]}")
    return d


# The twelve originals' bands. Local to z_dbz_fighters_ai.lua, so read off the
# literal -- it is a flat id = number table and nothing else in the file
# matches the surrounding shape.
RANK_RE = re.compile(r"local RANK = \{(.*?)\n\}", re.S)


def load_rank(errors):
    path = os.path.join(AUTORUN, "server/z_dbz_fighters_ai.lua")
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        errors.append(f"cannot read the AI file: {e}")
        return {}
    m = RANK_RE.search(src)
    if not m:
        errors.append("RANK table not found in z_dbz_fighters_ai.lua")
        return {}
    return {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", m.group(1))}


AI_PATH = "server/z_dbz_fighters_ai.lua"


def load_scaling(errors):
    """The exponents and clamps the AI file applies to a tier rating.

    Read rather than assumed: health and damage taking the SAME root is the
    thing that keeps time-to-kill constant up the ladder, and if that ever
    changes in Lua the site must not keep quoting the old numbers.
    """
    out = {"healthPow": 0.5, "damagePow": 0.5, "healthMax": 1e9, "ratingMax": 1e15,
           "rungGains": [], "namedRungs": {}}
    try:
        src = open(os.path.join(AUTORUN, AI_PATH), encoding="utf-8", errors="replace").read()
    except OSError as e:
        errors.append(f"cannot read the AI file for scaling: {e}")
        return out

    m = re.search(r"local TIER_HEALTH_POW\s*=\s*([0-9.]+)", src)
    if m:
        out["healthPow"] = float(m.group(1))
    else:
        errors.append("TIER_HEALTH_POW not found; assuming 0.5")
    # TIER_DAMAGE_POW is written as an alias of the health one.
    m = re.search(r"local TIER_DAMAGE_POW\s*=\s*(TIER_HEALTH_POW|[0-9.]+)", src)
    out["damagePow"] = (out["healthPow"] if (m and m.group(1) == "TIER_HEALTH_POW")
                        else (float(m.group(1)) if m else out["healthPow"]))
    m = re.search(r"local TIER_RATING_MAX\s*=\s*([0-9.e+]+)", src)
    if m:
        out["ratingMax"] = float(m.group(1))
    m = re.search(r"TIER_HEALTH_POW\),\s*1,\s*([0-9.e+]+)\)", src)
    if m:
        out["healthMax"] = float(m.group(1))

    m = re.search(r"local RUNG_GAINS = \{(.*?)\n\}", src, re.S)
    if m:
        out["rungGains"] = [{"cvar": c, "mult": float(v)} for c, v in
                            re.findall(r'\{\s*"([^"]+)",\s*([0-9.]+)', m.group(1))]
    else:
        errors.append("RUNG_GAINS not found; the form ladder will show no multipliers")
    m = re.search(r"local NAMED_RUNGS = \{(.*?)\n\}", src, re.S)
    if m:
        out["namedRungs"] = {k: {"cvar": c, "mult": float(v)} for k, c, v in
                             re.findall(r'(\w+)\s*=\s*\{\s*"([^"]+)",\s*([0-9.]+)', m.group(1))}
    return out


def load_spread(errors):
    """dbz_tier_spread's default -- the per-tier power step."""
    for name in ("z_dbz_fighters.lua", "server/z_dbz_fighters_ai.lua"):
        try:
            src = open(os.path.join(AUTORUN, name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = re.search(r'["\']dbz_tier_spread["\']\s*,\s*"?([0-9.]+)', src)
        if m:
            return float(m.group(1))
    errors.append("dbz_tier_spread default not found; assuming 2")
    return 2.0


# ---------------------------------------------------------------------------
# Tier letters
# ---------------------------------------------------------------------------

# The bands are a real ladder 0..30, and a letter is only a coarse read of it.
# Cut points are chosen so each letter holds a group you can actually scan and
# so the apex (band 30, Gogeta SSJ4, placed above Beerus on request) gets its
# own letter rather than being lost in with the rest.
TIER_CUTS = [
    ("Z", 30, 99, "Apex. Above everything, by request."),
    ("X", 24, 29, "World-ending. Two tiers clear of the next letter."),
    ("S", 20, 23, "Elite. Fusions and the top of the originals."),
    ("A", 16, 19, "Excellent. Wins most of the roster on stats alone."),
    ("B", 12, 15, "Good. Dangerous, but has a ceiling."),
    ("C", 8,  11, "Average. Mid-ladder; reads as a fair fight."),
    ("D", 4,   7, "Weak. Outclassed by anything above C."),
    ("F", 0,   3, "Stock. Band 0 is shipped stats, unscaled."),
]
TIER_ORDER = [t[0] for t in TIER_CUTS]

KI_FULL = []


def tier_letter(band):
    for letter, lo, hi, _ in TIER_CUTS:
        if lo <= band <= hi:
            return letter
    return "F"


# ---------------------------------------------------------------------------
# Abilities
# ---------------------------------------------------------------------------

# Prose for the ability types. The hero JSON says what a power IS mechanically
# (dps, cooldown, range) but never what it feels like, so the one-liner per
# TYPE is written here; the numbers beside it all come from the file.
TYPE_INFO = {
    "beam":       ("Beam",         "Held continuous beam. Damage is per second for as long as it is kept on target."),
    "projectile": ("Projectile",   "Thrown or fired. Travels, then deals its damage on impact."),
    "form":       ("Transformation", "Changes form: new aura, new stats, and for most a new body."),
    "toggle":     ("Toggle",       "Switched on and stays on until switched off."),
    "buff":       ("Buff",         "Self-directed. Charges ki or raises output for a while."),
    "teleport":   ("Movement",     "Closes distance instantly, usually to behind the target."),
    "dash":       ("Rush",         "Crosses the gap under its own power and hits on arrival."),
    "slam":       ("Slam",         "A single heavy hit on whatever is already in reach."),
    "ground":     ("Shockwave",    "Driven into the floor. Catches everything standing nearby."),
    "area":       ("Area",         "Goes off around the caster and hits outward in every direction."),
    "cone":       ("Cone",         "Sweeps a wedge in front of the caster rather than a single line."),
    "control":    ("Erasure",      "Does not injure -- removes. Scales past health entirely."),
    "devour":     ("Devour",       "Consumes the target outright. No projectile, no travel time."),
    "stance":     ("Stance",       "Swaps which weapon the melee chains come from. No damage of its own."),
}

PRETTY_FIX = {
    "ki": "Ki", "ssj": "SSJ", "dbz": "DBZ", "bt3": "BT3",
    "lssj": "LSSJ", "ui": "UI", "gt": "GT", "dps": "DPS",
}


def pretty(ident):
    words = []
    for w in re.split(r"[_\s]+", str(ident)):
        if not w:
            continue
        words.append(PRETTY_FIX.get(w.lower(), w[:1].upper() + w[1:]))
    return " ".join(words)


def fmt_mult(v):
    """x50 rather than x50.0; the Lua writes these as whole numbers."""
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def power_name(hero, pid, power):
    """Best name first: the power's own, then the hero's en text, then the id."""
    if isinstance(power, dict) and isinstance(power.get("name"), str) and power["name"]:
        return power["name"]
    entry = (hero.get("text") or {}).get("power_" + str(pid))
    if isinstance(entry, dict) and entry.get("en"):
        return entry["en"]
    if isinstance(entry, str) and entry:
        return entry
    return pretty(pid)


# The three utilities every Budokai Tenkaichi fighter is handed on top of its
# ki list -- z_dbz_bt3.lua take()s these by name right after the ki loop.
BT3_UTILITIES = ("aura", "charge_ki", "teleport")


def abilities_of(hero, wanted=None, ai_spells=None):
    """The fighter's arsenal, as flat rows.

    `wanted` replicates z_dbz_bt3.lua's power build for a borrowed roster
    entry: the ids on its ki list that the donor actually has, in that order,
    then the three utilities. take() skips an id the donor lacks, so a short
    list here is a donor that does not own the move, not an error.

    `disabled` / `hidden` are NOT filtered out. They mark a move FRITAS
    borrowed from another character and leaves off the player's wheel by
    default -- but an NPC casts straight from ai.spells with no such check
    (ENT:Cast only asks whether PowerById has the id), so these fighters do
    throw them, and a site that hid them would be describing a different
    roster than the one in the game.
    """
    by_id = {}
    for p in hero.get("powers") or []:
        if isinstance(p.get("id"), str):
            by_id.setdefault(p["id"], p)

    if wanted is None:
        order = [p.get("id") for p in hero.get("powers") or []]
    else:
        order = [i for i in wanted if i in by_id] + list(BT3_UTILITIES)

    spells = set(ai_spells or ())
    out, seen = [], set()
    for pid in order:
        p = by_id.get(pid)
        if not p or pid in seen:
            continue
        seen.add(pid)
        kind = p.get("type") or "other"
        label, blurb = TYPE_INFO.get(kind, (pretty(kind), ""))
        row = {
            "id": pid,
            "name": power_name(hero, pid, p),
            "type": kind,
            "typeLabel": label,
            "blurb": blurb,
            "group": p.get("group") or "",
        }
        if p.get("extra"):
            row["borrowed"] = True
        if pid in spells:
            row["ai"] = True
        # Only the figures the file actually carries. A missing cooldown is
        # left out rather than defaulted, so the page never shows a 0 that
        # was never written down.
        for src, dst in (("dps", "dps"), ("damage", "damage"), ("cooldown", "cooldown"),
                         ("range", "range"), ("count", "count"), ("radius", "radius"),
                         ("speed", "speed"), ("windup", "windup"), ("charge", "charge")):
            v = p.get(src)
            if isinstance(v, (int, float)):
                row[dst] = v
        if isinstance(p.get("color"), list):
            row["color"] = p["color"][:3]
        out.append(row)
    return out


def melee_of(hero):
    m = hero.get("melee") or {}
    rows = []
    for key, label in (("combo", "Ground"), ("airCombo", "Air")):
        seq = m.get(key)
        if not isinstance(seq, list):
            continue
        for i, step in enumerate(seq, 1):
            if not isinstance(step, dict):
                continue
            rows.append({
                "chain": label,
                "step": i,
                "name": pretty(re.sub(r"^melee_(air_)?", "", str(step.get("clip") or ""))) or f"{label} {i}",
                "damage": step.get("damage"),
                "forward": step.get("forward"),
                "up": step.get("up"),
            })
    return rows


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def power_profile(band, spread, scale, base_health):
    """What a band is worth in the fight, by the AI file's own arithmetic.

    rating = spread ** band, and health and damage each take rating ** 0.5 --
    so a tier gap tells in both directions at once and time-to-kill stays
    constant up the ladder. Health is clamped where it is applied because
    SetHealth has to fit an integer.
    """
    rating = min(spread ** band, scale["ratingMax"])
    mult   = rating ** scale["healthPow"]
    dmg    = rating ** scale["damagePow"]
    hp     = None
    if isinstance(base_health, (int, float)) and base_health > 0:
        hp = int(min(max(round(base_health * mult), 1), scale["healthMax"]))
    return rating, mult, dmg, hp


def write_census(errors):
    """
    The wider census -- every spawnable character in the whole addon tree.

    Kept in its own file rather than folded into data.json: it is an order of
    magnitude more rows than the roster, it answers a different question, and
    nothing on the tier pages depends on it.  Written pretty-printed for the
    same reason data.json is -- it is committed, and a diff nobody can read is
    a diff nobody checks.
    """
    try:
        import census
        rows = census.census()
    except Exception as ex:
        errors.append("census scan failed: %s" % ex)
        return

    packs = {}
    for row in rows:
        key = (row["pack"], row["ws"])
        packs[key] = packs.get(key, 0) + 1

    families = {}
    for row in rows:
        families[row["family"]] = families.get(row["family"], 0) + 1

    data = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"),
        "counts": {
            "characters": len(rows),
            "packs": len(packs),
            "families": families,
            "withHealth": sum(1 for r in rows if r.get("health")),
            "sprites": sum(1 for r in rows if r.get("sprite")),
        },
        "packs": [
            {"pack": p, "ws": w, "count": n}
            for (p, w), n in sorted(packs.items(), key=lambda kv: (-kv[1], kv[0][0].lower()))
        ],
        "characters": rows,
    }

    with open(os.path.join(ROOT, "census.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")

    print("census.json: %d characters across %d packs (%s)" % (
        len(rows), len(packs),
        ", ".join("%d %s" % (n, f) for f, n in sorted(
            families.items(), key=lambda kv: -kv[1]))))


def main():
    errors = []
    heroes = load_fritas(errors)
    bt3    = load_bt3(errors)
    rank   = load_rank(errors)
    spread = load_spread(errors)
    scale  = load_scaling(errors)

    roster_rows = bt3.get("roster") or []
    # The default ki arsenal, read off the Lua rather than retyped: a move
    # added to KI_FULL has to reach the site without a second edit here.
    global KI_FULL
    KI_FULL = bt3.get("kiFull") or []
    if not KI_FULL:
        errors.append("BT3.KiFull came back empty -- fighters without their own "
                      "ki list will show no ki moves")
    fighters = []

    # --- FRITAS's twelve -------------------------------------------------
    for hid, band in sorted(rank.items(), key=lambda kv: -kv[1]):
        hero = heroes.get(hid)
        if not hero:
            errors.append(f"RANK names {hid}, but no hero definition was found for it")
            continue
        stats = hero.get("stats") or {}
        rating, hmult, dmult, ehp = power_profile(band, spread, scale, stats.get("health"))
        spells = (hero.get("ai") or {}).get("spells") or []
        allp   = abilities_of(hero, ai_spells=spells)
        forms  = [a for a in allp if a["type"] == "form" and a["id"] != "form_base"]
        fighters.append({
            "id": hid,
            "name": hero.get("name") or pretty(hid),
            "source": "fritas",
            "sourceLabel": "Hero Arsenal",
            "pack": hero.get("_packName") or "",
            "workshop": hero.get("_workshop") or "",
            "author": hero.get("author") or "",
            "band": band,
            "tier": tier_letter(band),
            "rating": rating,
            "healthMult": hmult,
            "damageMult": dmult,
            "health": stats.get("health"),
            "effectiveHealth": ehp,
            "walk": stats.get("walk"),
            "run": stats.get("run"),
            "jump": stats.get("jump"),
            "scale": stats.get("scale"),
            "model": (hero.get("suits") or [{}])[0].get("model") or "",
            "color": ((hero.get("colors") or {}).get("main") or [255, 255, 255, 255])[:3],
            "abilities": [a for a in allp if a["type"] != "form"],
            "forms": forms,
            "aiSpells": [i for i in spells if isinstance(i, str)],
            "melee": melee_of(hero),
            "suits": len([s for s in (hero.get("suits") or []) if not s.get("form")]),
        })

    # --- the Budokai Tenkaichi roster ------------------------------------
    for spec in roster_rows:
        donor = heroes.get(spec.get("donor"))
        if not donor:
            errors.append(f"{spec.get('id')} borrows {spec.get('donor')}, which was not found")
            continue
        stats = donor.get("stats") or {}
        band  = int(spec.get("band") or 0)
        rating, hmult, dmult, ehp = power_profile(band, spread, scale, stats.get("health"))
        # spec.ki or KI_FULL, exactly as z_dbz_bt3.lua resolves it.
        ki     = spec.get("ki")
        wanted = ki if isinstance(ki, list) else KI_FULL
        forms = []
        for f in spec.get("forms") or []:
            row = {
                "id": f.get("id") or "",
                "name": f.get("name") or pretty(f.get("id") or ""),
                "type": "form",
                "typeLabel": "Transformation",
            }
            for k in ("mult", "rung", "drain", "scale"):
                if isinstance(f.get(k), (int, float)):
                    row[k] = f[k]
            if f.get("body"):
                row["body"] = f["body"]
            if isinstance(f.get("color"), list):
                row["color"] = f["color"][:3]
            # A form row already says how it is reached; say what it is worth.
            # Kaioken rungs carry an absolute `mult` that REPLACES the running
            # total, while a `rung` takes its gain from the standard ladder and
            # compounds on whatever came before -- two different bargains, so
            # they get two different sentences.
            if isinstance(row.get("mult"), (int, float)):
                row["gain"] = float(row["mult"])
                row["absolute"] = True
                b = (f"Absolute x{fmt_mult(row['mult'])} -- replaces the running "
                     "total instead of compounding on it.")
                if row.get("drain"):
                    b += f" Costs {int(row['drain'])} health a second to hold."
                row["blurb"] = b
            elif isinstance(row.get("rung"), (int, float)):
                rungs = scale.get("rungGains") or []
                i = int(row["rung"]) - 1
                g = rungs[i]["mult"] if 0 <= i < len(rungs) else None
                if g:
                    row["gain"] = float(g)
                    row["blurb"] = (f"Ladder rung {int(row['rung'])}, worth "
                                    f"x{fmt_mult(g)}, compounding on whatever "
                                    "came before it.")
                else:
                    row["blurb"] = TYPE_INFO["form"][1]
            else:
                row["blurb"] = TYPE_INFO["form"][1]
            forms.append(row)
        col = spec.get("color")
        fighters.append({
            "id": spec.get("id"),
            "name": spec.get("name") or pretty(spec.get("id") or ""),
            "source": "bt3",
            "sourceLabel": "Budokai Tenkaichi 3",
            "pack": "DRAGON BALL Z BUDOKAI TENKAICHI 3: GMOD Models",
            "workshop": "3693724216",
            "author": "RandomOne",
            "band": band,
            "tier": tier_letter(band),
            "rating": rating,
            "healthMult": hmult,
            "damageMult": dmult,
            "health": stats.get("health"),
            "effectiveHealth": ehp,
            "walk": stats.get("walk"),
            "run": stats.get("run"),
            "jump": stats.get("jump"),
            "scale": spec.get("scale"),
            "model": spec.get("model") or "",
            "donor": spec.get("donor"),
            "donorName": donor.get("name") or "",
            "color": (col[:3] if isinstance(col, list)
                      else ((donor.get("colors") or {}).get("main") or [255, 255, 255, 255])[:3]),
            "abilities": [a for a in abilities_of(
                              donor, wanted=wanted, ai_spells=wanted)
                          if a["type"] != "form"],
            "aiSpells": list(wanted),
            "forms": forms,
            "melee": melee_of(donor),
            "suits": 1,
        })

    fighters.sort(key=lambda f: (-f["band"], f["name"].lower()))

    # --- tiers ------------------------------------------------------------
    tiers = []
    for letter, lo, hi, note in TIER_CUTS:
        members = [f["id"] for f in fighters if f["tier"] == letter]
        tiers.append({
            "letter": letter, "lo": lo, "hi": hi, "note": note,
            "count": len(members), "members": members,
        })

    # --- the ability index (which fighters share a move) -------------------
    by_ability = {}
    for f in fighters:
        for a in f["abilities"] + f["forms"]:
            key = a["name"]
            slot = by_ability.setdefault(key, {
                "name": key, "type": a["type"], "typeLabel": a["typeLabel"],
                "blurb": a.get("blurb", ""), "users": [],
            })
            slot["users"].append(f["id"])
            # A shared move is the same move, but the fighter throwing it is
            # not -- a donor's figures scale with whoever borrowed it.  Keep
            # the strongest of each figure seen so the index reads as the
            # roster's ceiling for that move, and carry the flags through.
            for k in ("dps", "damage", "gain", "drain", "cooldown",
                      "windup", "charge", "range", "radius", "speed", "count"):
                v = a.get(k)
                if isinstance(v, (int, float)) and (slot.get(k) is None or v > slot[k]):
                    slot[k] = v
            if a.get("absolute"):
                slot["absolute"] = True
            if not slot.get("blurb") and a.get("blurb"):
                slot["blurb"] = a["blurb"]
    index = sorted(by_ability.values(), key=lambda a: (-len(a["users"]), a["name"].lower()))

    data = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "spread": spread,
        "scaling": scale,
        "tierOrder": TIER_ORDER,
        "fighters": fighters,
        "tiers": tiers,
        "abilityIndex": index,
        "counts": {
            "fighters": len(fighters),
            "fritas": sum(1 for f in fighters if f["source"] == "fritas"),
            "bt3": sum(1 for f in fighters if f["source"] == "bt3"),
            "abilities": len(index),
            "forms": sum(len(f["forms"]) for f in fighters),
            "bands": len({f["band"] for f in fighters}),
        },
        "errors": errors,
    }

    write_census(errors)

    out = os.path.join(ROOT, "data.json")
    with open(out, "w", encoding="utf-8") as fh:
        # Pretty-printed on purpose: this file is committed, and a ten-minute
        # cron that only ever produces one-line diffs is unreviewable.
        json.dump(data, fh, indent=1)
        fh.write("\n")

    c = data["counts"]
    print(f"data.json: {c['fighters']} fighters "
          f"({c['fritas']} Hero Arsenal + {c['bt3']} Tenkaichi), "
          f"{c['abilities']} distinct abilities, {c['forms']} transformations, "
          f"{c['bands']} bands")
    for e in errors:
        print("  ! " + e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
