# Titobi Studio storefront

Store site for Titobi Studio, live at titobi.com (GitHub Pages). Checkout goes through the
Titobi Shopify store (`heddnt-d1`).

## Run locally

    cd ~/titobi-site
    python3 scripts/serve.py        # http://127.0.0.1:8920/ (caching off)

## Where content comes from

| What | Source | Script |
|---|---|---|
| Products: names, copy, dimensions, finishes | the Gazelle session's `shopify/products.json`, the same data that goes into Shopify. A durable copy is kept in `.private/` (not published). | `python3 scripts/build_catalog.py` |
| Prices, Shopify variant IDs | `data/commerce.json` (hand-edited) | merged by `build_catalog.py` |
| Product photos, dimension drawings, line drawings, hero/scene images | `~/Desktop/Gazelle Collection/web/images/`, built to `.private/IMAGE_NEEDS.md` | `python3 scripts/sync_media.py` |
| 3D models | `~/Desktop/Gazelle Collection/models/` | `sync_media.py` |
| Lookbook | `~/Desktop/Gazelle Collection/web/lookbook/` → `lookbook/` | `sync_media.py` |
| Home copy, hero picks, typologies | `data/site.json` | – |
| Interim hero photos | Ben's real shop photos in `media/photos/` | – |

`sync_media.py` copies only what the Gazelle session has marked final in its STATUS.md:
- `web images final: <slugs> (<views>)` for product and site images
- `A: glbs final` for the 3D models
- `lookbook final` for the lookbook web export

Rerun it whenever a new line appears. Old renders (`renders/_superseded-*`) are never used.
`HOLD_SLUGS` / `HOLD_FILES` at the top of the script freeze pieces or files at the copy the site already has,
whatever STATUS says, until the Gazelle session sends an explicit release. Clear the entry, rerun, push.
`build_catalog.py` has the matching `HOLD_COPY` for those pieces' product copy; clear both together.
A piece's all-finish views (`<view>-<wood>`) need both its release line and a later
`- HH:MM G: QA <slug> all-finish PASS` with no `all-finish FAIL` since; until then the live copy stays.
Pages show a light grey tile with the typology line drawing wherever an image isn't released yet.

## Pages

- `index.html`: hero band → TYPOLOGIES → "Titobi means BIG." → product grid → hero band → footer
- `collection.html?c=<handle>`: 4-column shop grid
- `product.html?p=<slug>&finish=<finish>`:
  - left: sticky info and accordions
  - right: stacked gallery (hero, front, back, rear, side, details), then the 3D viewer
  - picking a finish swaps every photo in the gallery (Ben, Oct 15 2026): `<view>.jpg` is the default
    finish, `<view>-<finish>.jpg` the others, the hero's are `finish-<finish>.jpg`. A view not yet shot in
    that finish is hidden; the hero falls back to the default with "(photo coming)". Drawings don't change.
- Room scenes (home hero-1a, the About band) get a Baltic Birch / Walnut / Wenge switch (Ben, Oct 15 2026),
  birch on every load. Files: `_site/<scene>-walnut.jpg`, `-wenge.jpg` (hero-1a's are `scene-hero-*`). The
  switch shows only once at least one wood version is synced.
- `page.html?p=about|contact|info|lookbook`

The DWR deck is not on the site (Ben, Oct 13 2026). No downloads anywhere on the site: no file links,
no Downloads page or accordion (Ben, Oct 14 2026). The 3D viewer and the drawings shown on pages stay.

## Checkout

The cart is kept in `localStorage`. Checkout opens a Shopify cart permalink,
`https://heddnt-d1.myshopify.com/cart/<variantId>:<qty>,...`. It's turned on only when every line has a
variant ID in `data/commerce.json`. Real orders also need the Shopify store launched.

A piece can be shown but kept off sale: `"<slug>": {"for_sale": false}` in `data/commerce.json` (or a
`NOT FOR SALE` note in the source's `pending`). Its page says "In development" instead of a price, has no Add to cart,
and the cart drops it. The High Chair stays off sale until it is tested and certified as a children's product;
its copy makes no safety claims.

## Publishing

`main` is served by GitHub Pages. Preview: https://benergy80.github.io/titobi.com/ (no custom domain yet).
To go live on titobi.com: Max's GoDaddy DNS gets the four GitHub A records + `www` CNAME to
`benergy80.github.io`, then add a `CNAME` file containing `titobi.com` and enforce HTTPS in the Pages settings.
Run the build/sync scripts, check locally, run `python3 scripts/stamp_version.py` (cache-busts CSS/JS),
then commit and push. `.private/` is git-ignored and holds
internal material: the raw product source with notes, the Shopify theme reference and the image spec.
