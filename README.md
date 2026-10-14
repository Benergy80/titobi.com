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
Pages show a light grey tile with the typology line drawing wherever an image isn't released yet.

## Pages

- `index.html`: hero band → TYPOLOGIES → "Titobi means BIG." → product grid → hero band → footer
- `collection.html?c=<handle>`: 4-column shop grid
- `product.html?p=<slug>&finish=<finish>`:
  - left: sticky info and accordions
  - right: stacked gallery (hero, front, back, rear, side, details), then the 3D viewer
- `page.html?p=about|contact|info|downloads|lookbook`

The DWR deck is not on the site (Ben, Oct 13 2026).

## Checkout

The cart is kept in `localStorage`. Checkout opens a Shopify cart permalink,
`https://heddnt-d1.myshopify.com/cart/<variantId>:<qty>,...`. It's turned on only when every line has a
variant ID in `data/commerce.json`. Real orders also need the Shopify store launched.

## Publishing

`main` is served by GitHub Pages. Preview: https://benergy80.github.io/titobi.com/ (no custom domain yet).
To go live on titobi.com: Max's GoDaddy DNS gets the four GitHub A records + `www` CNAME to
`benergy80.github.io`, then add a `CNAME` file containing `titobi.com` and enforce HTTPS in the Pages settings.
Run the build/sync scripts, check locally, run `python3 scripts/stamp_version.py` (cache-busts CSS/JS),
then commit and push. `.private/` is git-ignored and holds
internal material: the raw product source with notes, the Shopify theme reference and the image spec.
