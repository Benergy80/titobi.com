#!/usr/bin/env python3
"""Copy finished Gazelle media into the site, but only what STATUS.md says is final.

The Gazelle Claude session writes to ~/Desktop/Gazelle Collection/ and posts lines to its
STATUS.md board. This script copies only what those lines release (see IMAGE_NEEDS.md):

  "- HH:MM web images final: <slug>, <slug> (<view>, <view>)"   releases web/images/<slug>/<view>.*
  "- HH:MM web images final: _site/hero-1a.jpg"                 releases one file by path
        -> media/products/<slug>/ or media/site/ (big stills resized to 1600 px wide)
  "- HH:MM ... HOLD <slug>/<file> ..."   withholds that file until a later release line names it again
  QA_GATES below: files that also need a pass line (e.g. "G: hero-1a PASS") before they're copied;
  any later QA FAIL line naming a file ("G: scene-work FAIL", "3 FAIL (bench/line ...; ...)"), or a QA line's
  running "Open: a/b, set.jpg ..." list, withholds it until a newer release line names it again.
  "<slugs> (all views ...)" releases every file in those slugs' folders.
  "- HH:MM lookbook final ..."     web/lookbook/ -> lookbook/
  "- HH:MM A: glbs final"          models/gazelle-<slug>.glb -> media/models/<slug>.glb
                                   (and per-finish gazelle-<slug>--<finish>.glb, if made)
  A file rewritten more than 2 min after the line that released it is work in progress: the copy the
  site already has stays, until a newer line releases it.

Then it rewrites data/media.json, which the pages read to decide what to show.
Never reads renders/_superseded-*.
"""
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from fnmatch import fnmatch
from pathlib import Path

GAZELLE = Path.home() / "Desktop" / "Gazelle Collection"
STATUS = Path("/private/tmp/claude-501/-Users-benstagl/5b215239-d211-4003-b1ce-bd27d3421684/scratchpad/STATUS.md")
SITE = Path(__file__).resolve().parent.parent
MEDIA = SITE / "media"
MAX_W = 1600
GRACE_S = 120  # a release line's HH:MM is posted just after its files are written
STAMP = r"^- \d{1,2}:\d{2} "  # milestone lines start "- HH:MM "; quoted mentions elsewhere don't count
WEB_IMG = re.compile(STAMP + r".*?(?:web images|(?<![\w-])line) final:\s*(.+)")  # D posts drawings as "line final: <slug> (...)"
SITE_VIEWS = {"lineup"}  # listed under a piece's views but they live in _site (the collection lineup)
SLUG_VIEWS = re.compile(r"(?<![\w./-])((?:[a-z0-9-]+,\s*)*[a-z0-9-]+)\s*\(([a-z0-9*, -]+)(?:;[^()]*)?\)")  # views end at ";" notes  # "armchair, stool (line, hero)"
PATH_ITEM = re.compile(r"(?<![\w.-])(_site|[a-z0-9-]+)/([a-z0-9*][\w*-]*)(?:\.(?:jpg|jpeg|png|svg|mp4))?")  # "_site/hero-1a.jpg", "bench/line"
ALL_VIEWS = re.compile(r"(?<![\w./-])((?:[a-z0-9-]+,\s*)*[a-z0-9-]+)\s*\(all views[^()]*\)")  # "stool, bench (all views, details ...)"
OPEN_BARE = re.compile(r"(?<![\w/.-])([a-z0-9-]+)\.(?:jpg|jpeg|png|svg)\b")  # "set.jpg" in a QA "Open:" list
HOLD = re.compile(r"\bHOLD\s+((?:(?:_site|[a-z0-9-]+)/[\w.*-]+[\s,]*)+)")  # "HOLD a/b.png a/b.svg", "HOLD x and HOLD y"
# Extra sign-off some files need, per the Gazelle session (Oct 13 2026).
QA_GATES = {("_site", "hero-1a"): "hero-1a"}

# Held at the Gazelle session's request until it says "released": the site keeps exactly the copy it has now
# (nothing added, replaced or removed), whatever STATUS says. Clear an entry when they release it.
HOLD_SLUGS: set[str] = set()  # e.g. {"tower"}: whole pieces (photos, drawings, GLB)
HOLD_FILES: set[tuple[str, str]] = set()  # (folder, stem-glob)


# A piece's all-finish views also need "- HH:MM G: QA <slug> all-finish PASS" after their release line, with no
# "... all-finish FAIL" since (a FAIL waits for a new release line and a new PASS). Until then the live copy stays.
ALL_FINISH = re.compile(r"(?:front|back|rear|side|detail-[12])-(?:baltic-birch|walnut|white-oak|wenge|maple)")
PENDING_QA: set[tuple[str, str]] = set()  # filled by released_files
# Photos the Gazelle session asked to gate the same way: a release of <slug>'s photos (defaults and finish heroes too)
# at or after the time waits for that PASS. Oct 16 2026: tower re-flatten at 06:20 (the 00:21 copy stays meanwhile).
# Clear the entry once the gated photos are live.
GATED_FROM = {"tower": datetime(2026, 10, 16, 6, 20).timestamp()}
PHOTO = re.compile(r"(?:hero|front|back|rear|side|detail-[12])(?:-[a-z-]+)?|finish-[a-z-]+")


def held(folder: str, stem: str) -> bool:
    return (folder in HOLD_SLUGS or (folder, stem) in PENDING_QA
            or any(f == folder and fnmatch(stem, pat) for f, pat in HOLD_FILES))


def all_finish_passed(lines: list[str], slug: str, released_at: int) -> bool:
    verdicts = [m.group(1) for l in lines[released_at + 1:]
                if (m := re.match(STAMP + rf"G: QA {re.escape(slug)} all-finish (PASS|FAIL)\b", l))]
    return "PASS" in verdicts and "FAIL" not in verdicts


def status_lines() -> list[str]:
    return STATUS.read_text().splitlines() if STATUS.exists() else []


def line_times(lines: list[str]) -> list[float | None]:
    """Epoch time of each "- HH:MM" line. The board only has clock times, so the last line is dated by
    STATUS.md's mtime and each jump back of more than 6 h, reading upward, is a day earlier."""
    out: list[float | None] = [None] * len(lines)
    if not STATUS.exists():
        return out
    day = datetime.fromtimestamp(STATUS.stat().st_mtime).replace(hour=0, minute=0, second=0, microsecond=0)
    later = None
    for i in range(len(lines) - 1, -1, -1):
        m = re.match(r"^- (\d{1,2}):(\d{2}) ", lines[i])
        if not m:
            continue
        t = day.replace(hour=int(m.group(1)), minute=int(m.group(2)))
        if later is not None and t > later + timedelta(hours=6):
            day -= timedelta(days=1)
            t -= timedelta(days=1)
        out[i] = t.timestamp()
        later = t
    return out


def unreleased(src: Path, released_at: float | None) -> bool:
    """True when the file was rewritten after the line that released it (work in progress, not yet announced)."""
    return released_at is not None and src.stat().st_mtime > released_at + GRACE_S


def posted(lines: list[str], milestone: str) -> bool:
    return any(re.match(STAMP + r"(?:[A-Z]: )?" + re.escape(milestone), l) for l in lines)


def qa_item(token: str) -> tuple[str, str] | None:
    token = token.strip().rstrip(":")
    if "/" in token:
        folder, stem = token.split("/", 1)
        return folder, re.sub(r"\.\w+$", "", stem)
    if re.match(r"(typology|scene|hero)-", token):
        return "_site", token
    return None


def qa_failures(line: str) -> list[tuple[str, str]]:
    """Files a QA line fails: "G: scene-work FAIL ..." or "G: ... 3 FAIL (bench/line ...; scene-work: ...) / 13 PASS"."""
    if not re.match(STAMP + r"G: ", line):
        return []
    single = re.match(STAMP + r"G: (\S+) FAIL", line)
    if single:
        return [k for k in [qa_item(single.group(1))] if k]
    block = re.search(r"\d+ FAIL \((.*?)\)\s*/", line)
    if not block:
        return []
    return [k for k in (qa_item(item.split()[0]) for item in block.group(1).split(";") if item.strip()) if k]


def qa_open(line: str, state: dict[tuple[str, str], bool]) -> list[tuple[str, str]]:
    """Files still failing per a QA line's running "Open: a/b, set.jpg + _site/c.jpg (note), slug x5" list.
    Paths count; a bare file name counts when it matches exactly one released file; "slug xN" can't be resolved."""
    if not re.match(STAMP + r"G: ", line) or "Open:" not in line:
        return []
    text = line.split("Open:", 1)[1]
    keys = [(f, re.sub(r"\.\w+$", "", stem)) for f, stem in PATH_ITEM.findall(text)]
    for stem in OPEN_BARE.findall(text):
        hits = [k for k in state if k[1] == stem]
        keys += hits if len(hits) == 1 else []
    return keys


def stems_on_disk(slug: str) -> list[str]:
    d = GAZELLE / "web" / "images" / slug
    return sorted({f.stem for f in d.iterdir() if f.is_file() and not f.name.startswith((".", "_"))}) if d.is_dir() else []


def released_files(lines: list[str]) -> dict[tuple[str, str], int]:
    """(folder, stem-pattern) pairs that are released and not on hold, in board order -> index of the releasing line."""
    state: dict[tuple[str, str], bool] = {}
    released_at: dict[tuple[str, str], int] = {}
    for i, line in enumerate(lines):
        if not re.match(STAMP, line):
            continue
        m = WEB_IMG.search(line)
        if m:
            text = re.sub(r"\[[^\]]*\]", "", m.group(1).split(" — ")[0])  # drop "[= hero]" notes
            text = re.sub(r"\b([a-z][a-z-]*-)(\d+)/(\d+)\b", r"\1\2, \1\3", text)  # "detail-line-1/2"
            keys = [(slug, stem) for slugs in ALL_VIEWS.findall(text) for slug in re.split(r",\s*", slugs)
                    for stem in stems_on_disk(slug)]
            for slugs, views in SLUG_VIEWS.findall(text):
                for view in (v.split()[0] for v in re.split(r"\s*,\s*", views.strip()) if v.strip()):  # "detail-line-2 ticks removed"
                    keys += [("_site", view)] if view in SITE_VIEWS else [(slug, view) for slug in re.split(r",\s*", slugs)]
            bare = text
            while re.search(r"\([^()]*\)", bare):  # path items outside the (notes)
                bare = re.sub(r"\([^()]*\)", " ", bare)
            keys += [k for k in PATH_ITEM.findall(bare) if not k[1].startswith("_")]
            for key in keys:
                state[key] = True
                released_at[key] = i
        for hold in HOLD.finditer(line):
            for key in PATH_ITEM.findall(hold.group(1)):
                state[key] = False
        for key in qa_failures(line) + qa_open(line, state):
            state[key] = False
    released = {k: released_at[k] for k, ok in state.items() if ok}
    for key, name in QA_GATES.items():
        if key not in released:
            continue
        passed = any(re.match(STAMP + "G: ", l) and re.search(rf"\b{re.escape(name)}( v\d+)? PASS", l)
                     for l in lines[released_at[key] + 1:])
        if not passed:
            del released[key]
    times = line_times(lines)
    for (folder, stem), i in list(released.items()):
        if folder == "_site":
            continue
        stems = [s for s in stems_on_disk(folder) if fnmatch(s, stem)] if "*" in stem else [stem]
        gated = folder in GATED_FROM and times[i] is not None and times[i] >= GATED_FROM[folder]
        pending = ({(folder, s) for s in stems if ALL_FINISH.fullmatch(s) or (gated and PHOTO.fullmatch(s))}
                   if not all_finish_passed(lines, folder, i) else set())
        if not pending:
            continue
        PENDING_QA.update(pending)
        if "*" not in stem:
            del released[(folder, stem)]
    return released


def model_release_times(lines: list[str], times: list[float | None]) -> dict[str, float]:
    """slug -> time of the latest "X: glbs final ..." line naming gazelle-<slug>.glb, the slug, or ALL."""
    out: dict[str, float] = {}
    slugs = sorted({g.stem.removeprefix("gazelle-") for g in (GAZELLE / "models").glob("gazelle-*.glb")}, key=len)
    for line, t in zip(lines, times):
        if t is None or not re.match(STAMP + r"(?:[A-Z]: )?.*glbs final", line):
            continue
        named = [s for s in slugs if re.search(rf"(?:gazelle-|(?<![\w-])){re.escape(s)}(?![\w-])", line)]
        if re.search(r"\bALL\b", line) or not named:  # "glbs final: ALL 18 ..." / the first, bare "A: glbs final"
            named = slugs
        for s in named:
            out[s] = t
    return out


def newer(src: Path, dst: Path) -> bool:
    return not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime


def copy_image(src: Path, dst: Path) -> None:
    if not newer(src, dst):
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in {".jpg", ".jpeg", ".png"} and src.stat().st_size > 400_000:
        fmt = "png" if src.suffix.lower() == ".png" else "jpeg"
        subprocess.run(["sips", "-Z", str(MAX_W * 5 // 4), "-s", "format", fmt, *(["-s", "formatOptions", "84"] if fmt == "jpeg" else []),
                        str(src), "--out", str(dst)], check=True, capture_output=True)
    else:
        shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path, released_at: float | None = None) -> bool:
    """Replace dst with src. When any file in src was rewritten after its release line (an export in progress),
    keep the whole existing copy instead of mixing two exports."""
    if not (src / "index.html").exists():
        return False
    if dst.exists() and any(f.is_file() and unreleased(f, released_at) for f in src.rglob("*")):
        return True
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


REGISTER_MAX_PX = 4.0  # card hover crossfades hero -> line; beyond this median offset the drawing visibly swims


def off_register(slug_dir: Path) -> bool | None:
    """Median distance (px) from the line drawing's outer outline to the hero photo's silhouette edge, vs REGISTER_MAX_PX.
    None when it can't be measured (files missing, or numpy/scipy/Pillow not installed)."""
    hero, line = slug_dir / "hero.jpg", slug_dir / "line.png"
    if not (hero.exists() and line.exists()):
        return None
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except ImportError:
        return None
    photo = Image.open(hero).convert("L")
    ink = np.array(Image.open(line).convert("RGBA").resize(photo.size))[..., 3] > 40
    obj = np.array(photo) < 240
    edge_dist = ndimage.distance_transform_edt(~(obj ^ ndimage.binary_erosion(obj, iterations=2)))
    filled = ndimage.binary_fill_holes(ndimage.binary_closing(ink, iterations=3))
    outline = filled ^ ndimage.binary_erosion(filled, iterations=2)
    return bool(outline.any() and np.median(edge_dist[outline]) > REGISTER_MAX_PX)


def main() -> int:
    lines = status_lines()
    manifest = {"products": {}, "site": [], "models": [], "lookbook": False, "off_register": []}

    released = released_files(lines)
    times = line_times(lines)
    for folder in sorted({f for f, _ in released}):
        src_dir = GAZELLE / "web" / "images" / folder
        target = MEDIA / ("site" if folder == "_site" else f"products/{folder}")
        patterns = {stem: times[i] for (f, stem), i in released.items() if f == folder}
        names = []
        if src_dir.is_dir():
            for f in sorted(src_dir.iterdir()):
                if held(folder, f.stem):  # the copy already on the site is added back below
                    continue
                hits = [t for pat, t in patterns.items() if fnmatch(f.stem, pat)]
                if f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".svg", ".mp4", ".json"} or not hits:
                    continue
                if unreleased(f, max((t for t in hits if t), default=None)):
                    if (target / f.name).exists():  # keep the released copy we already have
                        names.append(f.name)
                    continue
                copy_image(f, target / f.name)
                names.append(f.name)
        if names:
            if folder == "_site":
                manifest["site"] = names
            else:
                manifest["products"][folder] = names
    # held files: keep whatever the site has now
    for d in [MEDIA / "site", *(MEDIA / "products").glob("*")]:
        folder = "_site" if d.name == "site" else d.name
        kept = [f.name for f in d.iterdir() if f.is_file() and held(folder, f.stem)] if d.is_dir() else []
        if kept:
            have = manifest["site"] if folder == "_site" else manifest["products"].setdefault(folder, [])
            have[:] = sorted(set(have) | set(kept))
    # drop anything copied earlier that is no longer released (held, failed QA)
    for d in [MEDIA / "site", *(MEDIA / "products").glob("*")]:
        if not d.is_dir():
            continue
        keep = set(manifest["site"] if d.name == "site" else manifest["products"].get(d.name, []))
        for f in d.iterdir():
            if f.name not in keep:
                f.unlink()
        if d.name != "site" and not any(d.iterdir()):
            d.rmdir()

    manifest["products"] = dict(sorted(manifest["products"].items()))
    # pieces whose hover drawing doesn't land on the photo: cards fall back to the front photo until it's redrawn
    manifest["off_register"] = sorted(slug for slug in manifest["products"] if off_register(MEDIA / "products" / slug))
    if manifest["off_register"]:
        print("line drawing out of register with hero (card hover disabled):", ", ".join(manifest["off_register"]))

    model_times = model_release_times(lines, times)
    if model_times:
        for glb in sorted((GAZELLE / "models").glob("gazelle-*.glb")):
            slug = glb.stem.removeprefix("gazelle-")
            if slug in {"desk-48", "dining-set-10"} or slug.startswith("showroom-"):  # stale files the Gazelle session said to ignore; room scenes aren't products
                continue
            dst = MEDIA / "models" / f"{slug}.glb"
            if slug in HOLD_SLUGS or unreleased(glb, model_times.get(slug)):  # rewritten since its glbs final line: keep what we have
                if dst.exists():
                    manifest["models"].append(slug)
                continue
            if newer(glb, dst):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(glb, dst)
            manifest["models"].append(slug)

    if posted(lines, "lookbook final"):
        lb_times = [t for line, t in zip(lines, times) if t is not None and re.match(STAMP + r"(?:[A-Z]: )?lookbook final", line)]
        manifest["lookbook"] = copy_tree(GAZELLE / "web" / "lookbook", SITE / "lookbook", max(lb_times, default=None))

    (SITE / "data" / "media.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"products {len(manifest['products'])}, site files {len(manifest['site'])}, models {len(manifest['models'])}, "
          f"lookbook {manifest['lookbook']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
