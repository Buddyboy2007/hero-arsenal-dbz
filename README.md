# Hero Arsenal DBZ — roster site

A GitHub Pages site for the Garry's Mod *Hero Arsenal Engine DBZ* roster:
every fighter, every ability, the tier list, and the transformation ladder.

**Live:** https://buddyboy2007.github.io/hero-arsenal-dbz/

## Nothing here is maintained by hand

The site is regenerated from the running Garry's Mod install every ten
minutes. There is no second copy of the roster to keep in sync, because a
second copy would silently go stale the moment the Lua changed.

| Source | How it is read |
| --- | --- |
| The 12 Hero Arsenal heroes | `tools/extract.py` opens the workshop `.gma` files and parses each `RegisterHeroJSON([=[ … ]=])` payload — already JSON, so it is exact. Only `lua/hero_arsenal_dbz/heroes/` is read, which avoids pulling 200 MB of models per item. |
| The 54 Tenkaichi fighters | `tools/dump_bt3.lua` **executes** `z_dbz_bt3.lua` under a stub harness and dumps its tables. Pattern-matching would have missed the whole forms layer — the Kaioken climbs and the per-character ladders are built by code, not written as data. |
| The tier maths | Lifted off the literals in `server/z_dbz_fighters_ai.lua`. A rename there surfaces as a build error rather than a wrong number on the page. |
| Every other character installed | `tools/census.py` walks all 484 `.gma` archives and reads the `lua/entities/` declarations, classifying by what each class **inherits** rather than what it is named. 1,631 spawnable characters across 153 addons, on the site's *Every Character* page. |

## The two rosters

They answer different questions and are deliberately kept apart:

* **`data.json` / the Roster, Tier List, Abilities and Forms pages** — the 66
  Dragon Ball fighters. These are the only characters the band ladder governs,
  so they are the only ones with a band, a tier letter and scaled figures.
* **`census.json` / the Every Character page** — everything else the install
  can spawn. No bands, because the band system is the Dragon Ball layer's and
  does not reach them; just what each pack actually declared.

A class is counted as a character when its `Base` chain reaches `base_nextbot`
(DrGBase and plain nextbots) or an `npc_vj_*_base` (VJ Base SNPCs). It is
dropped as abstract when another class is built on top of it. The scan is
cached against each archive's size and mtime, so a repeat run only re-reads
addons that changed — a full cold scan of the 102 GB tree takes under a
second, because the `.gma` file table is prefix-filtered and the model blobs
are never touched.

## Pipeline

```
tools/extract.py   GMod install  ->  data.json + census.json
tools/census.py    every .gma     ->  the installed-character census
tools/stamp.py     holds the timestamp still when nothing else changed
tools/build.py     data.json     ->  docs/*.html
tools/update.sh    all of the above, then commit + push if the tree is dirty
```

Run the whole thing once:

```bash
tools/update.sh && tail var/update.log
```

Build locally without publishing:

```bash
python3 tools/extract.py && python3 tools/build.py
```

## The ten-minute timer

```bash
tools/install-timer.sh      # installs + starts the systemd user timer
systemctl --user list-timers dbz-site
tail -f var/update.log
```

It only commits when the roster (or the generator) actually changed, so an
idle install produces no commits at all.

## Credits

Hero Arsenal Engine DBZ by **FRITAS**. Budokai Tenkaichi 3 models by
**RandomOne**. Character models by **SilkTeam** and contributors, credited
per pack on the site's *How It Works* page. The tier bands, scaling layer and
patch files are this project's own.
