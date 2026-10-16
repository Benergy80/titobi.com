#!/usr/bin/env python3
"""Build data/catalog.json from the Gazelle session's Shopify product draft.

Source of truth for names, copy, dimensions and finishes: the same products.json that the
other Claude session imports into Shopify (read-only here). Site-only data is merged on top:
  data/commerce.json  {"<slug>": {"price": cents, "variants": {"<finish-slug>": variantId}}}
Collections come from data/site.json.
"""
import json
import re
import sys
from pathlib import Path

SRC = Path("/private/tmp/claude-501/-Users-benstagl/5b215239-d211-4003-b1ce-bd27d3421684/scratchpad/shopify/products.json")
SITE = Path(__file__).resolve().parent.parent
DATA = SITE / "data"
BACKUP = SITE / ".private" / "source-products.json"  # has internal notes; kept out of the public repo

# Copy held with the media (sync_media.py HOLD_SLUGS) until the Gazelle session releases these pieces:
# their entries are kept exactly as in the current data/catalog.json. Clear together with HOLD_SLUGS.
HOLD_COPY = {"tower", "stool", "stool-with-back"}  # Oct 15: tower v11 top, two-ply stool seats

# product_type -> site collection handle
TYPE_TO_COLLECTION = {
    "chair": "seating", "high chair": "seating", "stool": "seating", "bench": "seating", "seating": "seating",
    "desk": "tables", "table": "tables",
    "storage": "home", "shelving": "home",
    "lamp": "lighting", "lighting": "lighting",
}


def finish_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    if not src.exists():
        src = BACKUP  # the other session's scratchpad is temporary
    raw = json.loads(src.read_text())
    if src != BACKUP:
        BACKUP.parent.mkdir(exist_ok=True)
        BACKUP.write_text(src.read_text())
    items = raw["products"] if isinstance(raw, dict) else raw
    commerce_path = DATA / "commerce.json"
    commerce = json.loads(commerce_path.read_text()) if commerce_path.exists() else {}

    products = []
    for p in items:
        slug = p["slug"]
        finishes = next((o["values"] for o in p.get("options", []) if o["name"].lower() == "finish"), [])
        ptype = (p.get("product_type") or "").lower()
        dims = p.get("dimensions") or {}
        extra = commerce.get(slug, {})
        products.append({
            "slug": slug,
            "handle": p.get("handle", slug),
            "name": p["title"],
            "type": p.get("product_type"),
            "collection": TYPE_TO_COLLECTION.get(ptype, "home"),
            "summary": p.get("short_description", ""),
            "description_html": p.get("description_html", ""),
            "dims_in": None if "TBD" in str(dims.get("label_in")) else dims.get("label_in"),
            "dims_mm": None if "TBD" in str(dims.get("label_mm")) else dims.get("label_mm"),
            "dims_order": dims.get("order"),
            "materials": p.get("materials", ""),
            "construction": p.get("construction", ""),
            "finishes": [finish_slug(f) for f in finishes],
            "default_finish": finish_slug(p.get("default_finish") or (finishes[0] if finishes else "")),
            "price": extra.get("price"),
            # off sale when commerce.json says so or the source marks it NOT FOR SALE (the high chair, until certified)
            "for_sale": extra.get("for_sale", True) and "NOT FOR SALE" not in str(p.get("pending", "")).upper(),
            "shopify_variants": extra.get("variants", {}),
        })

    current = json.loads((DATA / "catalog.json").read_text()) if (DATA / "catalog.json").exists() else {}
    live = {p["slug"]: p for p in current.get("products", [])}
    products = [live[p["slug"]] if p["slug"] in HOLD_COPY and p["slug"] in live else p for p in products]

    site = json.loads((DATA / "site.json").read_text())
    names = {}
    for p in items:
        for o in p.get("options", []):
            if o["name"].lower() == "finish":
                names.update({finish_slug(v): v for v in o["values"]})

    catalog = {
        "shop": site["shop"],
        "collections": site["collections"],
        "finishes": names,
        "products": products,
    }
    (DATA / "catalog.json").write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(products)} products from {src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
