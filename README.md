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

## Pipeline

```
tools/extract.py   GMod install  ->  data.json
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
