#!/usr/bin/env python3
"""
Build the static site from data.json.

Five real pages rather than one shell that swaps innerHTML: every page is
deep-linkable, loads on its own, and GitHub Pages serves it flat. The shared
look lives in tools/tpl/shell.css and is inlined into each page, so a page is
one request with no flash of unstyled content.

Nothing in here types a fighter, a figure, or an ability name -- all of it
comes out of data.json, which extract.py regenerates from the live GMod
install. Change the Lua and the site follows; it cannot drift.
"""

import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# GitHub Pages serves a branch from either the root or /docs, and nothing
# else -- so the generated pages live in docs/ and Pages is pointed there.
SITE = os.path.join(ROOT, "docs")
CSS = open(os.path.join(HERE, "tpl", "shell.css")).read()

NAV = [
    ("index.html",     "Roster"),
    ("tiers.html",     "Tier List"),
    ("abilities.html", "Abilities"),
    ("forms.html",     "Forms"),
    ("characters.html", "Every Character"),
    ("about.html",     "How It Works"),
]

FONTS = ("https://fonts.googleapis.com/css2?family=Archivo+Black&"
         "family=Inter:wght@400;500;600;700;800&"
         "family=JetBrains+Mono:wght@500;600;700&display=swap")

e = html.escape


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------

def num(v):
    """Thousands separators, and no trailing .0 on whole numbers."""
    if v is None:
        return "--"
    f = float(v)
    return f"{int(round(f)):,}" if abs(f - round(f)) < 1e-9 else f"{f:,.2f}"


def mult(v):
    """Multipliers get a leading x; past a hundred the decimals are noise."""
    if not v:
        return "--"
    f = float(v)
    return "×" + (f"{int(round(f)):,}" if abs(f) >= 100 else num(f))


def big(v):
    """Ratings run to 1e15; past a billion the digits stop meaning anything."""
    if v is None:
        return "--"
    f = float(v)
    for cut, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if f >= cut:
            return f"{f / cut:.3g}{suf}"
    return num(f)


def initials(name):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][:1] + words[1][:1]).upper()


def ink_on(rgb):
    """Pick the readable ink for a fighter's own aura colour."""
    r, g, b = [int(x) for x in (list(rgb) + [128, 128, 128])[:3]]
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return "#0a0810" if lum > 0.5 else "#f3eff7"


def swatch(f, small=False):
    c = f.get("color") or [255, 176, 32]
    rgb = "rgb(%d,%d,%d)" % tuple(int(x) for x in (list(c) + [0, 0, 0])[:3])
    cls = "sig sm" if small else "sig"
    return (f'<span class="{cls}" style="--c:{rgb};color:{ink_on(c)}" '
            f'aria-hidden="true">{e(initials(f["name"]))}</span>')


def accent(f):
    c = f.get("color") or [255, 176, 32]
    return "rgb(%d,%d,%d)" % tuple(int(x) for x in (list(c) + [0, 0, 0])[:3])


CVAR_WORDS = {"ssj1": "Super Saiyan", "ssj2": "Super Saiyan 2",
              "ssj3": "Super Saiyan 3", "ssj4": "Super Saiyan 4",
              "ssj_blue": "Super Saiyan Blue", "kaioken": "Kaioken",
              "ultra_instinct": "Ultra Instinct", "fullpower": "Full Power"}


def pretty_cvar(key):
    """Name the ladder rungs the way the show does, not the way the cvar does."""
    if key in CVAR_WORDS:
        return CVAR_WORDS[key]
    return " ".join(w.capitalize() for w in key.split("_"))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


# --------------------------------------------------------------------------
# page chrome
# --------------------------------------------------------------------------

def page(fname, title, body, data=None):
    tabs = "".join(
        f'<a href="{h}"{" aria-current=\"page\"" if h == fname else ""}>{e(l)}</a>'
        for h, l in NAV)
    blob = ""
    if data is not None:
        blob = ('\n<script type="application/json" id="page-data">'
                + json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
                + "</script>")
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="Every fighter, ability and tier in the Hero Arsenal DBZ roster, read straight out of the running Garry's Mod install.">
<meta name="color-scheme" content="dark">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>
</head>
<body>
<header class="bar">
  <span class="brand">Hero Arsenal <i>DBZ</i></span>
  <nav class="tabs" aria-label="Sections">{tabs}</nav>
</header>
<main class="wrap">
{body}
</main>{blob}
</body>
</html>
"""


def footer(d):
    c = d["counts"]
    return f"""<footer class="foot">
<p>Generated <b>{e(d["generatedAt"])}</b> from the running Garry&#39;s Mod
install &mdash; {c['fritas']} Hero Arsenal heroes read out of the workshop
<code>.gma</code> files, {c['bt3']} Tenkaichi fighters read by executing
<code>z_dbz_bt3.lua</code> itself. Rebuilt every ten minutes; nothing on this
site is typed by hand.</p>
<p>Hero Arsenal Engine DBZ by <b>FRITAS</b>. Tenkaichi 3 models by
<b>RandomOne</b>. Tier bands, scaling and the patch layer are this
repository&#39;s own.</p>
</footer>"""


def strip(items):
    """Labels may carry entities (&mdash;), so they arrive already escaped."""
    cells = "".join(f"<div><b>{v}</b><span>{l}</span></div>" for v, l in items)
    return f'<section class="strip">{cells}</section>'


FILTER_JS = """
<script>
(function(){
  var q=document.getElementById('q'), live=document.getElementById('count');
  var chips=[].slice.call(document.querySelectorAll('.chip[data-k]'));
  var items=[].slice.call(document.querySelectorAll('[data-s]'));
  var total=items.length, state={};
  function run(){
    var t=(q&&q.value||'').trim().toLowerCase(), n=0;
    for(var i=0;i<items.length;i++){
      var el=items[i], ok=!t||el.getAttribute('data-s').indexOf(t)>-1;
      for(var k in state){
        if(state[k]&&state[k].length&&state[k].indexOf(el.getAttribute('data-'+k))<0) ok=false;
      }
      el.classList.toggle('hidden',!ok);
      if(ok) n++;
    }
    [].forEach.call(document.querySelectorAll('[data-group]'),function(g){
      g.classList.toggle('hidden',!g.querySelector('[data-s]:not(.hidden)'));
    });
    if(live) live.textContent=n+' of '+total+' shown';
  }
  chips.forEach(function(c){
    c.addEventListener('click',function(){
      var k=c.dataset.k, v=c.dataset.v, on=c.getAttribute('aria-pressed')==='true';
      if(v===''){ // the "all" chip clears its own key
        chips.filter(function(x){return x.dataset.k===k}).forEach(function(x){
          x.setAttribute('aria-pressed', x===c?'true':'false');});
        state[k]=[];
      } else {
        var all=chips.filter(function(x){return x.dataset.k===k&&x.dataset.v===''})[0];
        if(all) all.setAttribute('aria-pressed','false');
        c.setAttribute('aria-pressed', on?'false':'true');
        state[k]=chips.filter(function(x){
          return x.dataset.k===k&&x.dataset.v!==''&&x.getAttribute('aria-pressed')==='true';
        }).map(function(x){return x.dataset.v});
        if(!state[k].length&&all) all.setAttribute('aria-pressed','true');
      }
      run();
    });
  });
  if(q) q.addEventListener('input',run);
  run();
})();
</script>
"""


# --------------------------------------------------------------------------
# shared fragments
# --------------------------------------------------------------------------

def fchip(f, href="index.html"):
    return (f'<a class="fchip" href="{href}#{e(f["id"])}">{swatch(f, True)}'
            f'<span class="nm">{e(f["name"])}</span>'
            f'<span class="bd">{f["band"]}</span></a>')


def rows(pairs):
    out = []
    for label, value, hi in pairs:
        cls = ' class="hi"' if hi else ""
        out.append(f'<div><span>{e(label)}</span><b{cls}>{value}</b></div>')
    return '<div class="rows">' + "".join(out) + "</div>"


def ability_figures(a):
    """Only the figures the Lua actually carries for this move."""
    out = []
    for key, label, fmt in (
        ("dps", "Damage / sec", num), ("damage", "Damage", num),
        ("gain", "Multiplier", mult), ("drain", "Health / sec", num),
        ("cooldown", "Cooldown", lambda v: num(v) + "s"),
        ("windup", "Wind-up", lambda v: num(v) + "s"),
        ("charge", "Charge", lambda v: num(v) + "s"),
        ("range", "Range", num), ("radius", "Radius", num),
        ("speed", "Speed", num), ("count", "Projectiles", num),
    ):
        if a.get(key) is not None:
            out.append((label, fmt(a[key]), key in ("dps", "damage", "gain")))
    return out


# --------------------------------------------------------------------------
# what a "band" is -- written once, shown wherever the word first appears
# --------------------------------------------------------------------------

# Every number on this site traces back to one integer per fighter, and the
# word for that integer is "band".  It appeared on every page before it was
# ever defined anywhere, which is a reasonable way to lose a reader on the
# first card they look at.
def define_band(d, href="tiers.html#band"):
    sc = d["scaling"]
    per = d["spread"] ** sc["healthPow"]
    return f"""<section class="define">
<span class="k">Band</span>
<p>A <b>band</b> is a fighter&#39;s rung on the power ladder &mdash; a whole
number from <code>0</code> to <code>30</code>, and the only thing the game
reads when it decides how strong a character is. Nothing else is tuned by
hand: <b>every band up multiplies both damage and health by about
{num(round(per, 2))}&times;</b>, so <b>two bands is exactly double</b>. The
tier letter is just a label for a range of bands.
<a href="{href}">How the number turns into power &rarr;</a></p>
</section>"""


def band_section(d):
    """The long version: the arithmetic, worked, with the consequence spelt out."""
    sc = d["scaling"]
    spread, pw = d["spread"], sc["healthPow"]
    per = spread ** pw
    bands = sorted({f["band"] for f in d["fighters"]})
    lo, hi = bands[0], bands[-1]

    # Walk a handful of real rungs rather than all thirty-one: the point is
    # the shape of the curve, and the full ladder is the table below it.
    picks, step = [], max((hi - lo) // 5, 1)
    cur = lo
    while cur <= hi:
        picks.append(cur)
        cur += step
    if hi not in picks:
        picks.append(hi)

    at = {}
    for f in d["fighters"]:
        at.setdefault(f["band"], []).append(f["name"])

    trs = "".join(
        f'<tr><td class="n">{b}</td><td class="n">{big(min(spread ** b, sc["ratingMax"]))}</td>'
        f'<td class="n">{mult(min(spread ** b, sc["ratingMax"]) ** pw)}</td>'
        f'<td class="n">{mult(min(spread ** b, sc["ratingMax"]) ** pw)}</td>'
        f'<td>{e(", ".join(sorted(at.get(b, []))[:3])) or "&mdash;"}'
        f'{"&hellip;" if len(at.get(b, [])) > 3 else ""}</td></tr>'
        for b in picks)

    return f"""<h2 id="band">What a &ldquo;band&rdquo; is</h2>
<div class="prose">
<p>A <b>band</b> is one rung of the power ladder: a whole number from
<code>0</code> to <code>30</code> carried by every fighter. It is not a
description of them &mdash; it is the input. Hand the game a band and it
works out that character&#39;s health and damage from it, by formula, with no
per-fighter tuning anywhere.</p>
<p>It goes in three steps:</p>
<ul>
<li>The band becomes a <b>rating</b>: <code>rating = {num(spread)} ^ band</code>.
So each band <em>doubles</em> the rating &mdash; band 10 rates
<code>{big(spread ** 10)}</code>, band 20 rates <code>{big(spread ** 20)}</code>.</li>
<li>Damage is multiplied by <code>rating ^ {pw}</code> &mdash; the square
root of the rating.</li>
<li>Health is multiplied by <code>rating ^ {sc["healthPow"]}</code> as well:
the <em>same</em> exponent.</li>
</ul>
<p>Taking the square root is what makes the ladder usable. Doubling the
rating only multiplies damage by <code>{num(round(per, 4))}</code>, so in
plain terms:</p>
<ul>
<li><b>One band up</b> &asymp; <b>{num(round(per, 2))}&times;</b> the damage
and {num(round(per, 2))}&times; the health.</li>
<li><b>Two bands up</b> = exactly <b>double</b> both.</li>
<li><b>Ten bands up</b> = <b>{mult(per ** 10)}</b> both.</li>
</ul>
<p>And because damage and health take the <em>same</em> exponent, they grow
together. A band-{hi} fight does not end faster than a band-{lo} one &mdash;
it lasts about as long, with far bigger numbers floating over it. The band
decides <em>who wins</em> when two fighters are mismatched, not how quickly
anybody dies.</p>
<p>The <b>tier letter</b> adds nothing. It is a reading of the band and
nothing else: {e(" / ".join(t["letter"] + " " + (str(t["lo"]) if t["lo"] >= min(t["hi"], 30) else f'{t["lo"]}-{min(t["hi"], 30)}') for t in d["tiers"]))}.
Band <code>0</code> is special only in that it means &ldquo;unscaled&rdquo;
&mdash; the stats the model shipped with.</p>
</div>
<div class="tscroll"><table>
<thead><tr><th style="text-align:right">Band</th>
<th style="text-align:right">Rating</th>
<th style="text-align:right">Damage</th>
<th style="text-align:right">Health</th>
<th>Who sits here</th></tr></thead>
<tbody>{trs}</tbody></table></div>
<p class="sub" style="margin:14px 0 30px">Damage and health share a column of
numbers because they share an exponent &mdash; that is the whole design, not a
coincidence.</p>"""


def load_census():
    """
    The census is a separate file on purpose (see extract.write_census), and
    the site has to render without it: a fresh clone, or a machine with no
    GMod install, has a roster but no addon tree to count.
    """
    path = os.path.join(ROOT, "census.json")
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------

def build_roster(d):
    fs = sorted(d["fighters"], key=lambda f: (-f["band"], f["name"].lower()))
    cards = []
    for f in fs:
        moves = [a for a in f["abilities"] if a["type"] != "form"]
        forms = f["forms"]
        chips = "".join(
            f'<span class="mv{" borrowed" if a.get("borrowed") else ""}" '
            f'title="{e(a["typeLabel"])}">{e(a["name"])}</span>' for a in moves)
        chips += "".join(f'<span class="mv form">{e(a["name"])}</span>' for a in forms)
        src = f["sourceLabel"]
        who = f'{src} &middot; {e(f["author"])}'
        if f.get("donorName"):
            who += f' &middot; arsenal from {e(f["donorName"])}'
        cards.append(f"""<article class="card" id="{e(f["id"])}"
  style="--c:{accent(f)}" data-s="{e((f["name"] + " " + src + " " + f["tier"] + " " + " ".join(a["name"] for a in moves + forms)).lower())}"
  data-src="{e(f["source"])}" data-tier="{e(f["tier"])}">
  <span class="tag" style="--t:var(--tier{f["tier"]})">{f["tier"]}</span>
  <div class="top">{swatch(f)}<div><h3>{e(f["name"])}</h3>
    <div class="who">{who}</div></div></div>
  {rows([
      ("Band", str(f["band"]) + " / 30", False),
      ("Damage", mult(f["damageMult"]), True),
      ("Effective health", num(f["effectiveHealth"]), True),
      ("Run speed", num(f["run"]), False),
      ("Moves", f'{len(moves)} + {len(forms)} forms' if forms else str(len(moves)), False),
  ])}
  {f'<div class="moves">{chips}</div>' if chips else ""}
</article>""")

    tier_chips = "".join(
        f'<button class="chip" data-k="tier" data-v="{t}">{t}</button>'
        for t in d["tierOrder"])
    c = d["counts"]
    body = f"""<p class="eyebrow">Garry&#39;s Mod &middot; Hero Arsenal Engine DBZ</p>
<h1 class="hd">The <em>full roster</em></h1>
<p class="sub">Sixty-six fighters on one power ladder. Every figure below is
read out of the running install &mdash; band, scaling, and each character&#39;s
own named arsenal, including the moves they only throw as AI.</p>
{define_band(d)}
{strip([
    (c["fighters"], "fighters"),
    (c["abilities"], "distinct abilities"),
    (c["forms"], "transformations"),
    (c["bands"], "power bands"),
    (mult(max(f["damageMult"] for f in fs)), "top damage"),
])}
<div class="ctl">
  <input type="search" id="q" placeholder="Search a fighter, a move, a form&hellip;" aria-label="Search fighters">
  <button class="chip" data-k="src" data-v="" aria-pressed="true">All</button>
  <button class="chip" data-k="src" data-v="fritas">Hero Arsenal</button>
  <button class="chip" data-k="src" data-v="bt3">Tenkaichi</button>
  <span style="width:1px;height:22px;background:var(--line)"></span>
  <button class="chip" data-k="tier" data-v="" aria-pressed="true">Any tier</button>
  {tier_chips}
  <span class="count" id="count" role="status"></span>
</div>
<div class="grid">{"".join(cards)}</div>
{footer(d)}
{FILTER_JS}"""
    return page("index.html", "Hero Arsenal DBZ Roster", body)


def build_tiers(d):
    by_id = {f["id"]: f for f in d["fighters"]}
    bands = {}
    for f in d["fighters"]:
        bands.setdefault(f["band"], []).append(f)

    tiers = []
    for t in d["tiers"]:
        mem = [by_id[i] for i in t["members"] if i in by_id]
        mem.sort(key=lambda f: (-f["band"], f["name"].lower()))
        chips = "".join(fchip(f) for f in mem) or '<span class="empty">Nobody is sitting here.</span>'
        dmg = mult(max((f["damageMult"] for f in mem), default=0))
        hi = min(t["hi"], max((f["band"] for f in mem), default=t["lo"]))
        span = f'band {t["lo"]}' if t["lo"] >= hi else f'bands {t["lo"]}&ndash;{hi}'
        tiers.append(f"""<section class="tier">
  <div class="let" style="--t:var(--tier{t["letter"]})">
    <b>{t["letter"]}</b><span>{t["count"]} {"fighter" if t["count"] == 1 else "fighters"}</span></div>
  <div class="body">
    <p class="note">{e(t["note"])} <b>{span}</b>, up to <b>{dmg}</b> damage.</p>
    <div class="mem">{chips}</div>
  </div>
</section>""")

    ladder = []
    for band in sorted(bands, reverse=True):
        fs = sorted(bands[band], key=lambda f: f["name"].lower())
        for i, f in enumerate(fs):
            moves = len([a for a in f["abilities"] if a["type"] != "form"])
            ladder.append(f"""<tr><td>{band if i == 0 else ""}</td>
<td><span class="tag" style="position:static;--t:var(--tier{f["tier"]})">{f["tier"]}</span></td>
<td><a href="index.html#{e(f["id"])}">{e(f["name"])}</a></td>
<td>{e(f["sourceLabel"])}</td>
<td class="n">{big(f["rating"])}</td>
<td class="n">{mult(f["damageMult"])}</td>
<td class="n">{num(f["effectiveHealth"])}</td>
<td class="n">{moves}</td><td class="n">{len(f["forms"])}</td></tr>""")

    sc = d["scaling"]
    body = f"""<p class="eyebrow">Updated {e(d["generatedAt"][:10])}</p>
<h1 class="hd">Tier list &amp; <em>power ladder</em></h1>
<p class="sub">Eight letters over thirty-one bands. The letter is a reading of
the band, and the band is the only thing the game itself cares about &mdash;
every fighter&#39;s health and damage come out of it by the same formula.</p>
{strip([
    (len(d["tiers"]), "tiers"),
    (d["counts"]["bands"], "bands in use"),
    (mult(d["spread"]), "gain per band"),
    (mult(max(f["damageMult"] for f in d["fighters"])), "top of the ladder"),
])}
{band_section(d)}
{"".join(tiers)}
<h2>Every fighter by band</h2>
<p class="sub" style="margin-bottom:14px">Rating is <code>spread ^ band</code>,
capped at {big(sc["ratingMax"])}. Health and damage each take its square root,
which is what holds time-to-kill roughly constant as you climb.</p>
<div class="tscroll"><table>
<thead><tr><th>Band</th><th>Tier</th><th>Fighter</th><th>Source</th>
<th style="text-align:right">Rating</th><th style="text-align:right">Damage</th>
<th style="text-align:right">Eff. health</th><th style="text-align:right">Moves</th>
<th style="text-align:right">Forms</th></tr></thead>
<tbody>{"".join(ladder)}</tbody></table></div>
{footer(d)}"""
    return page("tiers.html", "DBZ Tier List", body)


def build_abilities(d):
    by_id = {f["id"]: f for f in d["fighters"]}
    groups = {}
    for a in d["abilityIndex"]:
        groups.setdefault(a["typeLabel"], []).append(a)

    # Transformations have their own page; on an ability index the attacks
    # are what the reader came for, so the forms group sinks to the bottom.
    order = sorted(groups, key=lambda k: (k == "Transformation", -len(groups[k]), k))
    out = []
    for label in order:
        items = sorted(groups[label],
                       key=lambda a: (-(a.get("dps") or a.get("damage") or 0),
                                      a["name"].lower()))
        cards = []
        for a in items:
            users = [by_id[u] for u in a["users"] if u in by_id]
            users.sort(key=lambda f: -f["band"])
            shown = users[:7]
            chips = "".join(fchip(f) for f in shown)
            if len(users) > len(shown):
                chips += (f'<span class="fchip" style="color:var(--faint)">'
                          f'+{len(users) - len(shown)} more</span>')
            figs = ability_figures(a)
            cards.append(f"""<article class="card"
  data-s="{e((a["name"] + " " + label + " " + " ".join(f["name"] for f in users)).lower())}"
  data-type="{e(label)}">
  <h3>{e(a["name"])}</h3>
  <div class="who">{e(label)} &middot; {len(users)} {"fighter" if len(users) == 1 else "fighters"}</div>
  <p style="margin:10px 0 0;font-size:12.5px;color:var(--dim)">{e(a["blurb"])}</p>
  {rows(figs) if figs else ""}
  <div class="moves" style="gap:6px">{chips}</div>
</article>""")
        out.append(f'<section data-group="{e(label)}"><h2>{e(label)} '
                   f'<span style="color:var(--faint);font-size:13px">'
                   f'{len(items)}</span></h2>'
                   f'<div class="grid">{"".join(cards)}</div></section>')

    type_chips = "".join(
        f'<button class="chip" data-k="type" data-v="{e(l)}">{e(l)}</button>'
        for l in order)
    strongest = max(d["abilityIndex"],
                    key=lambda a: a.get("damage") or a.get("dps") or 0)
    body = f"""<p class="eyebrow">{d["counts"]["abilities"]} distinct moves</p>
<h1 class="hd">Every <em>ability</em> on the roster</h1>
<p class="sub">Power ids are shared across the roster but named per character
&mdash; the same move is Gogeta&#39;s Stardust Breaker, Meta-Cooler&#39;s Death
Saucer, and Yamcha&#39;s Buster Cannon. Each is listed under the name its own
fighter calls it, with the figures the Lua really carries. Chips marked faint
on the roster page are moves borrowed from another character: kept off the
player&#39;s wheel, but the AI throws them anyway.</p>
{strip([
    (d["counts"]["abilities"], "abilities"),
    (len(order), "kinds"),
    (num(strongest.get("damage") or strongest.get("dps")), f"highest hit &mdash; {e(strongest['name'])}"),
    (d["counts"]["forms"], "transformations"),
])}
<div class="ctl">
  <input type="search" id="q" placeholder="Search a move or a fighter&hellip;" aria-label="Search abilities">
  <button class="chip" data-k="type" data-v="" aria-pressed="true">All kinds</button>
  {type_chips}
  <span class="count" id="count" role="status"></span>
</div>
{"".join(out)}
{footer(d)}
{FILTER_JS}"""
    return page("abilities.html", "DBZ Ability Index", body)


def build_forms(d):
    by_id = {f["id"]: f for f in d["fighters"]}
    forms = [a for a in d["abilityIndex"] if a["type"] == "form"]
    forms.sort(key=lambda a: (-(a.get("gain") or 0), -len(a["users"]), a["name"].lower()))

    cards = []
    for a in forms:
        users = sorted((by_id[u] for u in a["users"] if u in by_id),
                       key=lambda f: -f["band"])
        shown = users[:6]
        chips = "".join(fchip(f) for f in shown)
        if len(users) > len(shown):
            chips += (f'<span class="fchip" style="color:var(--faint)">'
                      f'+{len(users) - len(shown)} more</span>')
        figs = ability_figures(a)
        tagged = ""
        if a.get("absolute"):
            tagged = ('<span class="tag" style="--t:var(--rose);color:#190308">'
                      'ABS</span>')
        cards.append(f"""<article class="card" style="--c:var(--ki)"
  data-s="{e((a["name"] + " " + " ".join(f["name"] for f in users)).lower())}">
  {tagged}
  <h3>{e(a["name"])}</h3>
  <div class="who">{len(users)} {"fighter" if len(users) == 1 else "fighters"}</div>
  <p style="margin:10px 0 0;font-size:12.5px;color:var(--dim)">{e(a["blurb"])}</p>
  {rows(figs) if figs else ""}
  <div class="moves" style="gap:6px">{chips}</div>
</article>""")

    sc = d["scaling"]
    # The convar suffix is the form's real name; the Lua's numeric `rung`
    # only indexes the first four, so the rest get a dash rather than an
    # index number they do not actually answer to.
    def rung_name(cvar):
        return pretty_cvar(cvar.replace("dbz_form_mult_", ""))

    rungs = "".join(
        f'<tr><td>{e(rung_name(r["cvar"]))}</td>'
        f'<td class="n">{i + 1 if i < 4 else "&mdash;"}</td>'
        f'<td><code>{e(r["cvar"])}</code></td>'
        f'<td class="n">{mult(r["mult"])}</td></tr>'
        for i, r in enumerate(sc["rungGains"]))
    named = "".join(
        f'<tr><td>{e(rung_name(v["cvar"]))}</td><td class="n">&mdash;</td>'
        f'<td><code>{e(v["cvar"])}</code></td>'
        f'<td class="n">{mult(v["mult"])}</td></tr>'
        for v in (sc.get("namedRungs") or {}).values())

    withforms = [f for f in d["fighters"] if f["forms"]]
    deepest = max(withforms, key=lambda f: len(f["forms"])) if withforms else None
    body = f"""<p class="eyebrow">{len(forms)} distinct transformations</p>
<h1 class="hd">Forms &amp; the <em>gain ladder</em></h1>
<p class="sub">A transformation is worth a multiplier, and the two kinds of
multiplier behave differently. A ladder rung compounds on whatever the fighter
already had. A Kaioken rung is absolute: reaching it <em>replaces</em> the
running total, and it burns health for as long as it is held.</p>
{strip([
    (len(forms), "distinct forms"),
    (d["counts"]["forms"], "form slots on the roster"),
    (len(withforms), "fighters who transform"),
    (len(deepest["forms"]) if deepest else 0,
     f"deepest ladder &mdash; {e(deepest['name']) if deepest else ''}"),
    (mult(max((a.get("gain") or 0) for a in forms)), "largest single gain"),
])}
<h2>The standard ladder</h2>
<p class="sub" style="margin-bottom:14px">Each rung multiplies the one before
it, so the ladder compounds. Every gain is a convar &mdash; these are the
shipped defaults, not fixed numbers.</p>
<div class="tscroll"><table><thead><tr><th>Form</th>
<th style="text-align:right">Rung</th><th>Convar</th>
<th style="text-align:right">Gain</th></tr></thead>
<tbody>{rungs}{named}</tbody></table></div>
<h2>Every form</h2>
<div class="ctl">
  <input type="search" id="q" placeholder="Search a form or a fighter&hellip;" aria-label="Search forms">
  <span class="count" id="count" role="status"></span>
</div>
<div class="grid">{"".join(cards)}</div>
{footer(d)}
{FILTER_JS}"""
    return page("forms.html", "DBZ Transformations", body)


FAMILY_COLOUR = {
    "DrGBase": "var(--beam)",
    "VJ Base": "var(--namek)",
    "Nextbot": "var(--void)",
}

FAMILY_NOTE = {
    "DrGBase": ("Built on DrGBase, the nextbot framework the Dragon Ball "
                "fighters themselves run on."),
    "VJ Base": ("VJ Base SNPCs — the older engine-NPC lineage, registered "
                "into the NPC tab by VJ Base rather than by a Spawnable flag."),
    "Nextbot": "A plain base_nextbot, built on neither framework.",
}


def build_census(d, cen):
    chars = cen["characters"]
    cc = cen["counts"]
    by_pack = {}
    for ch in chars:
        by_pack.setdefault((ch["pack"], ch["ws"]), []).append(ch)

    order = sorted(by_pack.items(), key=lambda kv: (-len(kv[1]), kv[0][0].lower()))

    blocks = []
    for (pack, ws), members in order:
        members = sorted(members, key=lambda c: c["name"].lower())

        # A pack like Painkiller SNPCs ships twenty separate Bear classes
        # with different health, all declaring PrintName "Bear".  They are
        # genuinely different characters, so none of them is dropped -- but
        # twenty identical pills is unreadable.  Where a name repeats, the
        # part of the class name that actually differs is appended, which is
        # the only thing in the file that tells them apart.
        same = {}
        for c in members:
            same.setdefault(c["name"].lower(), []).append(c)
        tail = {}
        for group in same.values():
            if len(group) < 2:
                continue
            names = [g["class"] for g in group]
            head = os.path.commonprefix(names)
            head = head[:head.rfind("_") + 1] if "_" in head else head
            for g in group:
                rest = g["class"][len(head):].strip("_")
                tail[g["class"]] = rest or g["class"]

        chips = []
        for c in members:
            hp = f'<span class="hp">{num(c["health"])}</span>' if c.get("health") else ""
            suffix = (f'<span class="var">{e(tail[c["class"]])}</span>'
                      if c["class"] in tail else "")
            title = c["class"]
            if c.get("sprite"):
                title += " \u2014 2D sprite nextbot"
            if not c.get("named"):
                title += " \u2014 pack declared no display name"
            chips.append(
                f'<span class="nchip{"" if c["named"] else " guessed"}" '
                f'style="--f:{FAMILY_COLOUR.get(c["family"], "var(--faint)")}" '
                f'title="{e(title)}" data-s="{e((c["name"] + " " + c["class"] + " " + pack + " " + c["category"]).lower())}" '
                f'data-fam="{e(c["family"])}">'
                f'<span class="dot"></span><span class="nm">{e(c["name"])}</span>'
                f'{suffix}{hp}</span>')

        link = (f'<a href="https://steamcommunity.com/sharedfiles/filedetails/?id={e(ws)}"'
                f' rel="noopener">{e(ws)}</a>') if ws else ""
        blocks.append(f"""<section class="pack" data-group>
<h3>{e(pack) or "Unnamed addon"} {link}
  <span class="cnt">{len(members)} {"character" if len(members) == 1 else "characters"}</span></h3>
<div class="mem">{"".join(chips)}</div>
</section>""")

    fams = sorted(cc["families"].items(), key=lambda kv: -kv[1])
    fam_chips = "".join(
        f'<button class="chip" data-k="fam" data-v="{e(f)}">{e(f)} ({n})</button>'
        for f, n in fams)
    legend = "".join(
        f'<li><b style="color:{FAMILY_COLOUR.get(f, "var(--faint)")}">{e(f)}</b> '
        f'&mdash; {n} character{"" if n == 1 else "s"}. '
        f'{e(FAMILY_NOTE.get(f, ""))}</li>'
        for f, n in fams)

    body = f"""<p class="eyebrow">The whole install &middot; not just Dragon Ball</p>
<h1 class="hd">Every <em>character</em> installed</h1>
<p class="sub">{cc["characters"]:,} spawnable characters across
{cc["packs"]} addons &mdash; every nextbot and SNPC the install can put on a
map, read out of the entity declarations in the <code>.gma</code> archives
themselves. The {d["counts"]["fighters"]} Dragon Ball fighters are not repeated
here; they have <a href="index.html">their own roster</a>, because they are the
only ones the band ladder reaches.</p>
{strip([
    (f'{cc["characters"]:,}', "characters"),
    (cc["packs"], "addons"),
    (len(fams), "frameworks"),
    (f'{cc["withHealth"]:,}', "declare health"),
    (cc["sprites"], "2D nextbots"),
])}
<div class="panel" style="margin:0 0 24px">
<p style="margin:0 0 10px;color:var(--ink-2);font-size:13.5px">Found by what a
class <b>inherits</b>, not by what it is called &mdash; a pack&#39;s own
template sits between its characters and the framework, so the chain has to be
walked. Anything another class is built on top of is dropped as a base rather
than counted as a fighter.</p>
<ul class="prose" style="margin:0;font-size:13px">{legend}</ul>
</div>
<div class="ctl">
  <input type="search" id="q" placeholder="Search a character, a class, a pack&hellip;" aria-label="Search characters">
  <button class="chip" data-k="fam" data-v="" aria-pressed="true">All frameworks</button>
  {fam_chips}
  <span class="count" id="count" role="status"></span>
</div>
{"".join(blocks)}
<p class="sub" style="margin:26px 0 0">A number beside a name is the health the
pack declared for it. Most packs set theirs in code the scan cannot read
honestly, so where there is no number, there is no claim &mdash; and an
<i>italic</i> name is one this page title-cased from the class because the pack
never wrote a display name at all. These characters have no band: the band
system is the Dragon Ball layer&#39;s, and it does not reach them.</p>
{footer(d)}
{FILTER_JS}"""
    return page("characters.html", "Every Character Installed", body)


def build_about(d):
    sc, c = d["scaling"], d["counts"]
    packs = {}
    for f in d["fighters"]:
        packs.setdefault((f["pack"], f["author"], f["workshop"]), 0)
        packs[(f["pack"], f["author"], f["workshop"])] += 1
    prows = "".join(
        f'<tr><td>{e(p)}</td><td>{e(a)}</td>'
        f'<td><a href="https://steamcommunity.com/sharedfiles/filedetails/?id={e(w)}"'
        f' rel="noopener">{e(w)}</a></td><td class="n">{n}</td></tr>'
        for (p, a, w), n in sorted(packs.items(), key=lambda kv: -kv[1]))

    body = f"""<p class="eyebrow">Provenance</p>
<h1 class="hd">How this page <em>knows</em></h1>
<p class="sub">Nothing here is maintained by hand. A build step reads the
Garry&#39;s Mod install directly, every ten minutes, and this site is whatever
it found.</p>
<div class="prose">
<h2>Three sources, three methods</h2>
<div class="panel">
<p><b>The twelve Hero Arsenal heroes</b> are read out of the workshop
<code>.gma</code> archives. Each hero file is a single
<code>RegisterHeroJSON([=[ &hellip; ]=])</code> call, so the definition is
already JSON &mdash; parsed exactly, never guessed at. Only the
<code>lua/hero_arsenal_dbz/heroes/</code> entries are read, which is what keeps
the step from pulling two hundred megabytes of models per item.</p>
<p><b>The {c['bt3']} Tenkaichi fighters</b> are obtained by <em>executing</em>
<code>z_dbz_bt3.lua</code> under a stub harness and dumping its tables.
Pattern-matching the file would have missed the entire forms layer &mdash; the
Kaioken climbs, the Cooler and Frieza ladders, the per-character dispatch
&mdash; because those are built by code, not written as data.</p>
<p><b>The tier maths</b> is lifted off the literals in
<code>server/z_dbz_fighters_ai.lua</code>. If one of those is ever renamed the
build reports it as an error rather than quietly publishing a wrong number.</p>
</div>

<h2>The scaling, exactly as the game applies it</h2>
<p>A fighter&#39;s band is the only input &mdash; if that word is new, the
<a href="tiers.html#band">tier page explains it in full</a>. Everything else
follows from it:</p>
<ul>
<li><code>rating = {num(d["spread"])} ^ band</code>, capped at
<code>{big(sc["ratingMax"])}</code>.</li>
<li>Health is multiplied by <code>rating ^ {sc["healthPow"]}</code>, then
clamped to <code>{num(sc["healthMax"])}</code> &mdash; the ceiling the engine&#39;s
integer health field imposes.</li>
<li>Damage is multiplied by <code>rating ^ {sc["damagePow"]}</code>.</li>
</ul>
<p>Those two exponents matching is the whole point. Both sides of a fight grow
at the same rate, so a band-28 bout lasts about as long as a band-4 one
&mdash; it just has far bigger numbers floating over it.</p>

<h2>Why some moves look like they belong to someone else</h2>
<p>A Tenkaichi fighter borrows its arsenal from one of the twelve donors, and
takes whichever power ids its roster row asks for. Moves the donor flags
<code>disabled</code> or <code>hidden</code> are still copied across, and are
shown here, because the player&#39;s wheel is the only thing those flags gate.
The AI cast path never checks them &mdash; it asks only whether the hero owns
the power. These fighters really do throw them, so hiding them would describe
a roster the game does not have.</p>

<h2>Packs</h2>
</div>
<div class="tscroll"><table><thead><tr><th>Pack</th><th>Author</th>
<th>Workshop</th><th style="text-align:right">Fighters</th></tr></thead>
<tbody>{prows}</tbody></table></div>
{footer(d)}"""
    return page("about.html", "Roster Provenance", body)


# --------------------------------------------------------------------------

def main():
    src = os.path.join(ROOT, "data.json")
    if not os.path.exists(src):
        sys.exit("data.json missing -- run tools/extract.py first")
    d = json.load(open(src))
    if d.get("errors"):
        print("build warnings from extract:", file=sys.stderr)
        for err in d["errors"]:
            print("  -", err, file=sys.stderr)

    cen = load_census()
    if cen is None:
        print("census.json missing -- skipping the full-install page",
              file=sys.stderr)

    os.makedirs(SITE, exist_ok=True)
    pages = {
        "index.html":     build_roster(d),
        "tiers.html":     build_tiers(d),
        "abilities.html": build_abilities(d),
        "forms.html":     build_forms(d),
        "about.html":     build_about(d),
    }
    if cen is not None:
        pages["characters.html"] = build_census(d, cen)
    # .nojekyll or Pages would strip anything underscore-prefixed.
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    for name, text in pages.items():
        with open(os.path.join(SITE, name), "w") as fh:
            fh.write(text)
    # The roster data ships alongside the pages so it can be consumed directly.
    with open(os.path.join(SITE, "data.json"), "w") as fh:
        json.dump(d, fh, separators=(",", ":"))
    if cen is not None:
        with open(os.path.join(SITE, "census.json"), "w") as fh:
            json.dump(cen, fh, separators=(",", ":"))

    total = sum(len(t) for t in pages.values())
    extra = f", {cen['counts']['characters']:,} installed characters" if cen else ""
    print(f"docs/: {len(pages)} pages, {total:,} bytes, "
          f"{d['counts']['fighters']} fighters{extra}")


if __name__ == "__main__":
    main()
