#!/usr/bin/env python3
"""Copy finished Gazelle media into the site, but only what STATUS.md says is final.

The Gazelle/Vectary Claude session writes to ~/Desktop/Gazelle Collection/ and posts lines to its
STATUS.md board. This script copies only what those lines release (see IMAGE_NEEDS.md):

  "- HH:MM web images final: <slug>, <slug> (<view>, <view>)"   releases web/images/<slug>/<view>.*
  "- HH:MM web images final: _site/hero-1a.jpg"                 releases one file by path
        -> media/products/<slug>/ or media/site/ (big stills resized to 1600 px wide)
  "- HH:MM ... HOLD <slug>/<file> ..."   withholds that file until a later release line names it again
  QA_GATES below: files that also need a pass line (e.g. "G: hero-1a PASS") before they're copied;
  any later QA FAIL line naming a file ("G: scene-work FAIL", "3 FAIL (bench/line ...; ...)") withholds it
  until a newer release line names it again.
  "- HH:MM lookbook final ..."     web/lookbook/ -> lookbook/
  "- HH:MM A: glbs final"          models/gazelle-<slug>.glb -> media/models/<slug>.glb
                                   (and per-finish gazelle-<slug>--<finish>.glb, if made)

Then it rewrites data/media.json, which the pages read to decide what to show.
Never reads renders/_superseded-*.
"""
import json
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

GAZELLE = Path.home() / "Desktop" / "Gazelle Collection"
STATUS = Path("/private/tmp/claude-501/-Users-benstagl/5b215239-d211-4003-b1ce-bd27d3421684/scratchpad/STATUS.md")
SITE = Path(__file__).resolve().parent.parent
MEDIA = SITE / "media"
MAX_W = 1600
STAMP = r"^- \d{1,2}:\d{2} "  # milestone lines start "- HH:MM "; quoted mentions elsewhere don't count
WEB_IMG = re.compile(STAMP + r".*?web images final:\s*(.+)")
SLUG_VIEWS = re.compile(r"(?<![\w./-])((?:[a-z0-9-]+,\s*)*[a-z0-9-]+)\s*\(([a-z0-9*, -]+)(?:;[^()]*)?\)")  # views end at ";" notes  # "armchair, stool (line, hero)"
PATH_ITEM = re.compile(r"(?<![\w.-])(_site|[a-z0-9-]+)/([a-z0-9*][\w*-]*)(?:\.(?:jpg|jpeg|png|svg|mp4))?")  # "_site/hero-1a.jpg", "bench/line"
HOLD = re.compile(r"\bHOLD\s+((?:(?:_site|[a-z0-9-]+)/[\w.*-]+[\s,]*)+)")  # "HOLD a/b.png a/b.svg", "HOLD x and HOLD y"
# Extra sign-off some files need, per the Gazelle session (Oct 13 2026).
QA_GATES = {("_site", "hero-1a"): "hero-1a"}


def status_lines() -> list[str]:
    return STATUS.read_text().splitlines() if STATUS.exists() else []


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


def released_files(lines: list[str]) -> set[tuple[str, str]]:
    """(folder, stem-pattern) pairs that are released and not on hold, in board order."""
    state: dict[tuple[str, str], bool] = {}
    released_at: dict[tuple[str, str], int] = {}
    for i, line in enumerate(lines):
        if not re.match(STAMP, line):
            continue
        m = WEB_IMG.search(line)
        if m:
            text = m.group(1).split(" — ")[0]
            keys = [(slug, view) for slugs, views in SLUG_VIEWS.findall(text)
                    for slug in re.split(r",\s*", slugs) for view in re.split(r",\s*", views.strip())]
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
        for key in qa_failures(line):
            state[key] = False
    released = {k for k, ok in state.items() if ok}
    for key, name in QA_GATES.items():
        if key not in released:
            continue
        passed = any(re.match(STAMP + "G: ", l) and re.search(rf"\b{re.escape(name)}( v\d+)? PASS", l)
                     for l in lines[released_at[key] + 1:])
        if not passed:
            released.discard(key)
    return released


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


def copy_tree(src: Path, dst: Path) -> bool:
    if not (src / "index.html").exists():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def main() -> int:
    lines = status_lines()
    manifest = {"products": {}, "site": [], "models": [], "lookbook": False}

    released = released_files(lines)
    for folder in sorted({f for f, _ in released}):
        src_dir = GAZELLE / "web" / "images" / folder
        target = MEDIA / ("site" if folder == "_site" else f"products/{folder}")
        patterns = [stem for f, stem in released if f == folder]
        names = []
        if src_dir.is_dir():
            for f in sorted(src_dir.iterdir()):
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".svg", ".mp4", ".json"} and any(fnmatch(f.stem, pat) for pat in patterns):
                    copy_image(f, target / f.name)
                    names.append(f.name)
        if names:
            if folder == "_site":
                manifest["site"] = names
            else:
                manifest["products"][folder] = names
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

    if any(re.match(STAMP + r"[A-Z]: (glbs final|all renders final)", l) for l in lines):
        for glb in sorted((GAZELLE / "models").glob("gazelle-*.glb")):
            slug = glb.stem.removeprefix("gazelle-")
            if slug in {"desk-48", "dining-set-10"}:  # stale files the Gazelle session said to ignore
                continue
            dst = MEDIA / "models" / f"{slug}.glb"
            if newer(glb, dst):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(glb, dst)
            manifest["models"].append(slug)

    if posted(lines, "lookbook final"):
        manifest["lookbook"] = copy_tree(GAZELLE / "web" / "lookbook", SITE / "lookbook")

    (SITE / "data" / "media.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"products {len(manifest['products'])}, site files {len(manifest['site'])}, models {len(manifest['models'])}, "
          f"lookbook {manifest['lookbook']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
