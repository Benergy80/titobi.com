/* Titobi Studio storefront. Renders pages from data/site.json, data/catalog.json and
   data/media.json; keeps a cart in localStorage; hands checkout to the Shopify store. */

const CART_KEY = "titobi-cart-v1";
const MODEL_VIEWER = "https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js";
const GALLERY_ORDER = ["hero", "front", "back", "rear", "side", "detail-1", "detail-2"];
const DRAWING_ORDER = ["line", "line-front", "line-side", "line-rear", "exploded-line", "detail-line-1", "detail-line-2"];

const S = { site: null, catalog: null, media: null, cart: null };
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const params = new URLSearchParams(location.search);

const ICONS = {
  search: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><circle cx="8.5" cy="8.5" r="6"/><path d="m13 13 4.5 4.5"/></svg>',
  cart: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="3.5" y="6.5" width="13" height="10.5" rx="2"/><path d="M7 6.5V5a3 3 0 0 1 6 0v1.5"/></svg>',
  close: '<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15"/></svg>',
  arrow: '<svg viewBox="0 0 22 12" width="18" height="10" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><path d="M0 6h20m-5-5 5 5-5 5"/></svg>',
};

/* ---------- data ---------- */

async function loadData() {
  const get = (u, fallback) => fetch(u).then((r) => (r.ok ? r.json() : fallback)).catch(() => fallback);
  [S.site, S.catalog, S.media] = await Promise.all([
    get("data/site.json"),
    get("data/catalog.json"),
    get("data/media.json", { products: {}, site: [], models: [], lookbook: false }),
  ]);
}

const products = () => S.catalog.products;
const productBySlug = (slug) => products().find((p) => p.slug === slug);
const collection = (handle) => S.site.collections.find((c) => c.handle === handle);
const finishName = (f) => S.catalog.finishes[f] || f;
const year = new Date().getFullYear();

function productFile(p, name) {
  const files = S.media.products[p.slug] || [];
  const hit = files.find((f) => f.replace(/\.[^.]+$/, "") === name);
  return hit ? `media/products/${p.slug}/${hit}` : null;
}
/* hero is shot in the piece's default finish; other finishes have their own finish-<finish> frame. */
function productImage(p, finish) {
  return (finish && productFile(p, `finish-${finish}`)) || productFile(p, "hero");
}
const defaultFinish = (p) => (p.finishes.includes(p.default_finish) ? p.default_finish : p.finishes[0]);
const SITE_EXT_ORDER = ["svg", "mp4", "jpg", "jpeg", "png", "json"];  // vector logo and video loops win over stills
function siteFile(name) {
  const hits = (S.media.site || []).filter((f) => f.replace(/\.[^.]+$/, "") === name);
  hits.sort((a, b) => SITE_EXT_ORDER.indexOf(a.split(".").pop()) - SITE_EXT_ORDER.indexOf(b.split(".").pop()));
  return hits.length ? `media/site/${hits[0]}` : null;
}
function typologyImage(handle) {
  return siteFile(`typology-${handle}`) || collection(handle)?.image;
}
/* 3D model for a piece. A finish can come as a KHR_materials_variants variant inside the one GLB
   (switched with model-viewer's variantName) or as its own file, models/<slug>--<finish>.glb. */
function modelSrc(p, finish) {
  if (finish && S.media.models.includes(`${p.slug}--${finish}`)) return `media/models/${p.slug}--${finish}.glb`;
  return S.media.models.includes(p.slug) ? `media/models/${p.slug}.glb` : null;
}
function showFinishIn3D(viewer, p, finish) {
  if (!viewer) return;
  if (viewer.availableVariants?.includes(finish)) { viewer.variantName = finish; return; }
  const src = modelSrc(p, finish);
  if (src && viewer.getAttribute("src") !== src) viewer.setAttribute("src", src);
}
function formatPrice(cents) {
  if (cents == null) return null;
  return new Intl.NumberFormat("en-US", { style: "currency", currency: S.site.shop.currency }).format(cents / 100);
}

/* ---------- cart ---------- */

function cartItems() {
  if (!S.cart) { try { S.cart = JSON.parse(localStorage.getItem(CART_KEY)) || []; } catch { S.cart = []; } }
  return S.cart;
}
function writeCart(items) {
  S.cart = items;
  try { localStorage.setItem(CART_KEY, JSON.stringify(items)); } catch { /* private mode: cart lasts for this page */ }
  renderCart();
}
function addToCart(slug, finish, qty) {
  const items = cartItems().slice();
  const hit = items.find((i) => i.slug === slug && i.finish === finish);
  if (hit) hit.qty += qty; else items.push({ slug, finish, qty });
  writeCart(items);
  openDrawer("cart");
}
function setQty(index, qty) {
  const items = cartItems().slice();
  if (qty <= 0) items.splice(index, 1); else items[index] = { ...items[index], qty };
  writeCart(items);
}

/* Shopify cart permalink: /cart/<variant>:<qty>,... opens the store's checkout with these lines. */
function checkoutUrl(items) {
  const parts = [];
  for (const i of items) {
    const variant = productBySlug(i.slug)?.shopify_variants?.[i.finish];
    if (!variant) return null;
    parts.push(`${variant}:${i.qty}`);
  }
  return parts.length ? `https://${S.site.shop.domain}/cart/${parts.join(",")}` : null;
}

function renderCart() {
  const items = cartItems().filter((i) => productBySlug(i.slug));
  const count = items.reduce((n, i) => n + i.qty, 0);
  const badge = $("#cart-count");
  if (badge) { badge.textContent = count; badge.hidden = count === 0; }
  const body = $("#cart-body");
  if (!body) return;
  body.innerHTML = items.length ? items.map((i, idx) => {
    const p = productBySlug(i.slug);
    const img = productImage(p, i.finish);
    const price = formatPrice(p.price != null ? p.price * i.qty : null);
    return `<div class="line">
      ${img ? `<img class="line__img" src="${img}" alt="">` : '<span class="line__img"></span>'}
      <div>
        <a href="product.html?p=${p.slug}&finish=${i.finish}">${esc(p.name)}</a>
        <div class="line__meta">${esc(finishName(i.finish))}${price ? ` · ${price}` : ""}</div>
        <div class="qty" data-idx="${idx}">
          <button type="button" data-step="-1" aria-label="Decrease quantity">−</button>
          <input type="number" min="0" value="${i.qty}" aria-label="Quantity">
          <button type="button" data-step="1" aria-label="Increase quantity">+</button>
        </div>
      </div>
      <button type="button" class="line__remove" data-remove="${idx}">Remove</button>
    </div>`;
  }).join("") : '<p class="empty">Your cart is empty.</p>';

  const priced = items.every((i) => productBySlug(i.slug).price != null);
  const total = items.reduce((s, i) => s + (productBySlug(i.slug).price ?? 0) * i.qty, 0);
  $("#cart-total").textContent = !items.length ? formatPrice(0) : priced ? formatPrice(total) : "Price on request";
  const url = checkoutUrl(items);
  const btn = $("#checkout");
  btn.disabled = !url;
  btn.textContent = items.length && !url ? "Checkout opens at launch" : "Check out";
  btn.dataset.url = url || "";
  $("#cart-note").textContent = items.length && !url
    ? "These pieces aren't connected to the Shopify store yet, so checkout is off for now."
    : "Shipping and taxes are calculated at checkout.";
}

/* ---------- chrome ---------- */

function headerHtml() {
  return `<header class="site-header">
    <a class="site-header__logo" href="index.html"><img src="${siteFile("logo") || "media/store/titobi-logo.png"}" alt="titobi" width="82" height="26"></a>
    <div class="site-header__tools">
      <button class="icon-btn" type="button" data-open="search" aria-label="Search">${ICONS.search}</button>
      <button class="icon-btn" type="button" data-open="cart" aria-label="Cart">${ICONS.cart}<span class="cart-count" id="cart-count" hidden>0</span></button>
    </div>
  </header>`;
}

function footerHtml() {
  return `<footer class="site-footer">
    <div class="site-footer__grid">
      <p>Titobi means BIG.<br>©${year} Titobi Studio, LLC<br>Chicago, Illinois</p>
      <p><a href="collection.html">Shop</a><br><a href="${S.media.lookbook ? "lookbook/index.html" : "page.html?p=lookbook"}">Lookbook</a><br><a href="page.html?p=downloads">Downloads</a><br><a href="page.html?p=info">Info + FAQs</a></p>
      <p><a href="page.html?p=about">About Us</a><br><a href="page.html?p=contact">Contact</a><br><a href="https://www.instagram.com/titobistudio" rel="noopener">Instagram</a></p>
      <form class="signup" id="signup" novalidate>
        <p>Sign up for our newsletter, Informal.</p>
        <div class="signup__field">
          <label class="visually-hidden" for="signup-email">Email address</label>
          <input id="signup-email" type="email" placeholder="Email address" autocomplete="email" required>
          <button type="submit" aria-label="Sign up">${ICONS.arrow}</button>
        </div>
        <div class="signup__note" id="signup-note" aria-live="polite"></div>
      </form>
    </div>
  </footer>`;
}

function drawersHtml() {
  return `<div class="scrim" id="scrim"></div>
  <aside class="drawer" id="drawer-cart" aria-label="Cart" aria-hidden="true">
    <div class="drawer__head"><span>Cart</span><button class="icon-btn" type="button" data-close aria-label="Close cart">${ICONS.close}</button></div>
    <div class="drawer__body" id="cart-body"></div>
    <div class="drawer__foot">
      <div class="drawer__total"><span>Subtotal</span><span id="cart-total"></span></div>
      <p class="drawer__note" id="cart-note"></p>
      <button class="btn" type="button" id="checkout">Check out</button>
    </div>
  </aside>
  <div class="search-panel" id="drawer-search" aria-hidden="true">
    <div class="search-panel__row">
      <label class="visually-hidden" for="search-input">Search</label>
      <input id="search-input" type="search" placeholder="Search" autocomplete="off">
      <button class="icon-btn" type="button" data-close aria-label="Close search">${ICONS.close}</button>
    </div>
    <div class="search-results" id="search-results"></div>
  </div>`;
}

function openDrawer(name) {
  closeDrawers();
  const el = $(`#drawer-${name}`);
  el.classList.add("is-open");
  el.setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("is-open");
  if (name === "search") { $("#search-input").focus(); runSearch(""); }
}
function closeDrawers() {
  document.querySelectorAll(".drawer, .search-panel").forEach((d) => { d.classList.remove("is-open"); d.setAttribute("aria-hidden", "true"); });
  $("#scrim")?.classList.remove("is-open");
}
function runSearch(q) {
  const term = q.trim().toLowerCase();
  const hits = products().filter((p) => !term || `${p.name} ${p.type} ${p.collection}`.toLowerCase().includes(term));
  $("#search-results").innerHTML = hits.length ? hits.map((p) => cardHtml(p, { price: false })).join("") : '<p class="empty">No matches.</p>';
}

function mountChrome() {
  $("#header").outerHTML = headerHtml();
  $("#footer").outerHTML = footerHtml();
  document.body.insertAdjacentHTML("beforeend", drawersHtml());

  document.addEventListener("click", (e) => {
    const open = e.target.closest("[data-open]");
    if (open) return openDrawer(open.dataset.open);
    if (e.target.closest("[data-close]") || e.target.id === "scrim") return closeDrawers();
    const rm = e.target.closest("[data-remove]");
    if (rm) return setQty(+rm.dataset.remove, 0);
    const step = e.target.closest(".drawer .qty [data-step]");
    if (step) {
      const idx = +step.parentElement.dataset.idx;
      return setQty(idx, cartItems()[idx].qty + +step.dataset.step);
    }
    if (e.target.id === "checkout" && e.target.dataset.url) location.href = e.target.dataset.url;
  });
  document.addEventListener("change", (e) => {
    const box = e.target.closest(".drawer .qty");
    if (box) setQty(+box.dataset.idx, Math.max(0, parseInt(e.target.value, 10) || 0));
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawers(); });
  $("#search-input").addEventListener("input", (e) => runSearch(e.target.value));
  $("#signup").addEventListener("submit", (e) => {
    e.preventDefault();
    $("#signup-note").textContent = $("#signup-email").checkValidity()
      ? "Thanks. Signups go live when the store launches." : "Enter a valid email address.";
  });
  renderCart();
}

/* ---------- shared pieces ---------- */

function cardHtml(p, { price = true } = {}) {
  // Photo first; hover shows the line drawing, which is drawn from the same camera so it lands in register.
  const drawing = drawingView() ? null : productFile(p, "line");
  const photo = drawingView() ? null : productImage(p) || productFile(p, "front");
  const imgs = [photo || productFile(p, "line"), photo && (drawing || productFile(p, "front"))].filter(Boolean);
  const media = imgs.length
    ? `<div class="card__media${photo ? "" : " is-drawing"}">${imgs.map((src, i) => `<img src="${src}" alt="${i ? "" : esc(p.name)}" loading="lazy">`).join("")}</div>`
    : `<div class="card__media is-placeholder"><img src="${typologyImage(p.collection)}" alt="" loading="lazy"></div>`;
  const cost = price && formatPrice(p.price);
  return `<li><a class="card" href="product.html?p=${p.slug}">${media}
    <div class="card__name">${esc(p.name)}</div>${cost ? `<div class="card__price">${cost} USD</div>` : ""}</a></li>`;
}

function heroPanel(name, fallback, caption, dark) {
  const src = siteFile(name) || fallback;
  if (caption && siteFile(name) && caption.when_final) caption = { ...caption, ...caption.when_final };
  const cap = caption ? `<p class="hero__caption${dark ? " hero__caption--dark" : ""}">${esc(caption.line)}<strong>${esc(caption.name)}</strong></p>` : "";
  const media = /\.mp4$/.test(src) ? `<video src="${src}" autoplay muted loop playsinline></video>` : `<img src="${src}" alt="">`;
  return caption?.link ? `<a class="hero__panel" href="${caption.link}">${media}${cap}</a>` : `<div class="hero__panel">${media}${cap}</div>`;
}

const drawingView = () => params.get("view") === "drawings";

async function loadLineup() {
  if (!(S.media.site || []).includes("lineup.json")) return null;
  try { return await fetch("media/site/lineup.json").then((r) => r.json()); } catch { return null; }
}

/* The whole collection in one row at true relative size; each piece links to its page. */
function lineupHtml(L) {
  const img = siteFile("lineup");
  if (!img || !L) return "";
  const links = L.pieces.map((pc) => {
    const p = productBySlug(pc.slug);
    if (!p) return "";
    const left = ((pc.x_centre_px - pc.width_px / 2) / L.width) * 100;
    const top = ((L.floor_y_px - pc.height_px) / L.height) * 100;
    return `<a class="lineup__hit" href="product.html?p=${p.slug}" style="left:${left}%;width:${(pc.width_px / L.width) * 100}%;top:${top}%;height:${(pc.height_px / L.height) * 100}%"><span>${esc(p.name)}</span></a>`;
  }).join("");
  return `<div class="lineup" style="aspect-ratio:${L.width} / ${L.height}"><img src="${img}" alt="The Gazelle Collection, all ${L.pieces.length} pieces at true relative size">${links}</div>`;
}

function sectionFigure() {
  const src = siteFile("ply-section");
  return src ? `<figure class="section-fig"><img src="${src}" alt="Edge section: two 18 mm plies glued to 36 mm, each with a 5/8 inch roundover"></figure>` : "";
}

/* ---------- pages ---------- */

function renderHome(main) {
  const h = S.site.home;
  main.innerHTML = `
    <section class="hero" aria-label="Gazelle Collection">
      ${heroPanel("hero-1a", h.hero.media[0], h.hero)}
      ${heroPanel("hero-1b", h.hero.media[1])}
    </section>
    <section class="typologies" aria-labelledby="typologies">
      <h2 id="typologies">TYPOLOGIES</h2>
      <ul>${S.site.collections.map((c) => `<li><a class="typology" href="collection.html?c=${c.handle}">
        <div class="typology__img"><img src="${typologyImage(c.handle)}" alt="" loading="lazy"></div><span>${esc(c.title)}</span></a></li>`).join("")}</ul>
    </section>
    <section class="statement">
      <p class="display">${esc(h.statement.text)}</p>
      <a href="${h.statement.link}">${esc(h.statement.link_label)}</a>
    </section>
    <ul class="grid grid--home" aria-label="The collection">${products().map((p) => cardHtml(p, { price: false })).join("")}</ul>
    <section class="hero" aria-label="Making">
      ${heroPanel("hero-2a", h.hero2.media[0])}
      ${heroPanel("hero-2b", h.hero2.media[1], h.hero2)}
    </section>`;
}

function renderCollection(main) {
  const col = collection(params.get("c"));
  const list = col ? products().filter((p) => p.collection === col.handle) : products();
  const title = col ? col.title : "Shop";
  document.title = `${title} – Titobi Studio`;
  main.innerHTML = `
    <div class="shop-head">
      <h1 class="display">${esc(title)}</h1>
      <nav class="shop-meta" aria-label="Typologies">
        <span>${list.length} item${list.length === 1 ? "" : "s"}</span>
        <a href="?${new URLSearchParams({ ...(col ? { c: col.handle } : {}) })}"${!drawingView() ? ' aria-current="page"' : ""}>Photos</a>
        <a href="?${new URLSearchParams({ ...(col ? { c: col.handle } : {}), view: "drawings" })}"${drawingView() ? ' aria-current="page"' : ""}>Drawings</a>
        <span aria-hidden="true">|</span>
        <a href="collection.html${drawingView() ? "?view=drawings" : ""}"${!col ? ' aria-current="page"' : ""}>All</a>
        ${S.site.collections.map((c) => `<a href="collection.html?c=${c.handle}${drawingView() ? "&view=drawings" : ""}"${col?.handle === c.handle ? ' aria-current="page"' : ""}>${esc(c.title)}</a>`).join("")}
      </nav>
    </div>
    ${!col ? `<div class="shop-lineup">${lineupHtml(S.lineup)}</div>` : ""}
    ${list.length ? `<ul class="grid grid--shop">${list.map((p) => cardHtml(p)).join("")}</ul>`
      : '<p class="gutter empty" style="padding-bottom:120px">Gazelle has no pieces in this typology yet.</p>'}`;
}

function renderProduct(main) {
  const p = productBySlug(params.get("p"));
  if (!p) { main.innerHTML = '<div class="text-page"><h1 class="display">Not found</h1><p><a href="collection.html">Back to the shop</a></p></div>'; return; }
  let finish = p.finishes.includes(params.get("finish")) ? params.get("finish") : defaultFinish(p);
  const model = modelSrc(p);
  const price = formatPrice(p.price);
  document.title = `${p.name} – Titobi Studio`;

  const views = GALLERY_ORDER.map((v) => [v, productFile(p, v)]).filter(([, src]) => src);
  const drawings = DRAWING_ORDER.map((v) => productFile(p, v)).filter(Boolean)
    .map((src) => `<div class="gallery__item is-drawing"><img src="${src}" alt="" loading="lazy"></div>`).join("");
  const photos = views.map(([v, src]) => `<div class="gallery__item"><img ${v === "hero" ? 'id="main-img" ' : ""}src="${v === "hero" ? productImage(p, finish) : src}" alt="${v === "hero" ? esc(p.name) : ""}" ${v === "hero" ? "" : 'loading="lazy"'}></div>`).join("");
  const gallery = photos + drawings || `<div class="gallery__item is-placeholder"><img src="${typologyImage(p.collection)}" alt=""></div>`;
  const viewer = model ? `<div class="gallery__item"><model-viewer src="${modelSrc(p, finish)}" camera-controls tone-mapping="agx" shadow-intensity="0.4" exposure="1.1" alt="3D model of the ${esc(p.name)}" loading="lazy"></model-viewer></div>` : "";
  const dims = productFile(p, "dims");
  const downloads = [
    model && `<a class="u" href="${model}" download>3D model (GLB)</a>`,
    productFile(p, "line") && `<a class="u" href="${productFile(p, "line")}" download>Line drawing</a>`,
    productFile(p, "exploded-line") && `<a class="u" href="${productFile(p, "exploded-line")}" download>Exploded drawing</a>`,
  ].filter(Boolean);

  main.innerHTML = `
    <div class="product">
      <div class="product__info"><div class="product__info-sticky"><div class="product__info-inner">
        <h1 class="display product__title">${esc(p.name)}</h1>
        <p class="product__price">${price ? `${price}` : "Price on request"}</p>
        <div class="product__desc"><p>${esc(p.summary)}</p></div>
        <div class="finish">
          <p>Finish: <span id="finish-name">${esc(finishName(finish))}</span></p>
          <div class="swatches" role="radiogroup" aria-label="Finish">
            ${p.finishes.map((f) => `<button type="button" class="swatch" role="radio" data-f="${f}" aria-checked="${f === finish}" aria-label="${esc(finishName(f))}" title="${esc(finishName(f))}" style="--sw:var(--f-${f})"></button>`).join("")}
          </div>
        </div>
        <button class="btn" type="button" id="add">Add to cart</button>
        <div class="accordion">
          <details><summary>Dimensions</summary><div class="acc-body">
            ${p.dims_in ? `<p>${esc(p.dims_in)}${p.dims_order ? ` (${esc(p.dims_order)})` : ""}<br>${esc(p.dims_mm || "")}</p>` : "<p>Dimensions to come.</p>"}
            ${dims ? `<img src="${dims}" alt="Dimension drawing of the ${esc(p.name)}">` : ""}
          </div></details>
          <details><summary>Materials + finishes</summary><div class="acc-body"><p>${esc(p.materials)}</p>${p.construction ? `<p>${esc(p.construction)}</p>` : ""}${sectionFigure()}</div></details>
          <details><summary>Downloads</summary><div class="acc-body">${downloads.length ? `<p>${downloads.join("<br>")}</p>` : "<p>Drawings and 3D files are on the way.</p>"}</div></details>
          <details><summary>Lead time, shipping, customization</summary><div class="acc-body"><p>Each piece is made to order in Chicago. Lead times, shipping and custom species or sizes will be listed here before the store opens. For now, write to us through the <a class="u" href="page.html?p=contact">contact page</a>.</p></div></details>
        </div>
      </div></div></div>
      <div class="gallery">${gallery}${viewer}</div>
    </div>`;

  if (model && !customElements.get("model-viewer")) {
    const s = document.createElement("script");
    s.type = "module"; s.src = MODEL_VIEWER;
    document.head.append(s);
  }
  const mv = main.querySelector("model-viewer");
  mv?.addEventListener("load", () => showFinishIn3D(mv, p, finish));
  main.addEventListener("click", (e) => {
    const sw = e.target.closest(".swatch");
    if (sw) {
      finish = sw.dataset.f;
      main.querySelectorAll(".swatch").forEach((b) => b.setAttribute("aria-checked", String(b === sw)));
      const pending = finish !== defaultFinish(p) && !productFile(p, `finish-${finish}`);
      $("#finish-name").textContent = finishName(finish) + (pending ? " (photo coming)" : "");
      const img = $("#main-img");
      if (img) img.src = finish === defaultFinish(p) ? productFile(p, "hero") || img.src : productImage(p, finish) || img.src;
      showFinishIn3D(mv, p, finish);
      history.replaceState(null, "", `?p=${p.slug}&finish=${finish}`);
    }
    if (e.target.id === "add") addToCart(p.slug, finish, 1);
  });
}

const PAGES = {
  about: () => `<h1 class="display">About</h1>
    <p>Titobi means BIG.</p>
    <p>Titobi Studio is a collaboration of Norman Teague Design Studios and Max Davis Design in Chicago.</p>
    <h2>The Gazelle Collection</h2>
    <p>Seventeen pieces for sitting, working and storing, all built the same way. Each is cut from 18 mm Baltic birch and laminated in pairs. Each ply gets a 5/8" roundover, so every edge shows its laminations as stripes that follow the outline.</p>
    ${sectionFigure()}`,
  contact: () => `<h1 class="display">Contact</h1>
    <p>Titobi Studio, LLC<br>Chicago, Illinois</p>
    <p>Instagram: <a href="https://www.instagram.com/titobistudio" rel="noopener">@titobistudio</a></p>`,
  info: () => `<h1 class="display">Info + FAQs</h1>
    <h2>Materials</h2><p>${esc(products()[0]?.materials || "")}</p>${sectionFigure()}
    <h2>Finishes</h2><p>${Object.values(S.catalog.finishes).map(esc).join(", ")}.</p>
    <h2>Lead time, shipping, returns</h2><p>Details will be posted before the store opens.</p>`,
  downloads: () => {
    const rows = products().filter((p) => modelSrc(p) || productFile(p, "line"));
    return `<h1 class="display">Downloads</h1>
      ${rows.length ? `<ul class="rows">${rows.map((p) => `<li><a href="product.html?p=${p.slug}">${esc(p.name)}</a><span>${[
        modelSrc(p) && `<a href="${modelSrc(p)}" download>GLB</a>`, productFile(p, "line") && `<a href="${productFile(p, "line")}" download>Drawing</a>`,
      ].filter(Boolean).join(" · ")}</span></li>`).join("")}</ul>` : "<p>Drawings and 3D files for the Gazelle Collection are on the way.</p>"}`;
  },
  lookbook: () => `<h1 class="display">Lookbook</h1>
    <p>${S.media.lookbook ? `<a href="lookbook/index.html">${esc(S.site.lookbook.title)}</a>` : "The Gazelle Collection lookbook is being finished and will be posted here."}</p>`,
};

function renderPage(main) {
  const key = params.get("p");
  const body = PAGES[key];
  document.title = `${body ? main.dataset.title || key[0].toUpperCase() + key.slice(1) : "Not found"} – Titobi Studio`;
  const scene = key === "about" && (siteFile("scene-work") || siteFile("scene-dining") || siteFile("scene-entry"));
  main.innerHTML = (scene ? `<div class="scene-band"><img src="${scene}" alt=""></div>` : "")
    + `<div class="text-page${scene ? " text-page--after-band" : ""}">${body ? body() : '<h1 class="display">Not found</h1>'}</div>`
    + (key === "about" && S.lineup ? `<div class="about-lineup">${lineupHtml(S.lineup)}</div>` : "");
}

/* ---------- boot ---------- */

(async () => {
  const page = document.body.dataset.page;
  await loadData();
  S.lineup = await loadLineup();
  mountChrome();
  ({ home: renderHome, collection: renderCollection, product: renderProduct, page: renderPage })[page]($("#main"));
})();
