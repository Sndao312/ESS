/* E.S.S. storefront client. All product, price, category, stock and order data
   comes from the same-origin server API; WooCommerce credentials never reach here. */
(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const CART_KEY = 'ess-store-cart-v2';
  const PAGE_SIZE = 18;
  const DEFAULT_PHONE = '+221777477778';
  const app = $('#app');

  const state = {
    settings: { brand: 'ELMANSOUR SUPPLIES & SERVICES', phone: DEFAULT_PHONE, whatsapp: '221777477778', currency: 'FCFA' },
    categories: [],
    home: null,
    homeFetchedAt: 0,
    cart: readCart(),
    lastFocus: null,
    sending: false,
    catalogRequest: 0,
  };

  function readCart() {
    try {
      const rows = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
      if (!Array.isArray(rows)) return [];
      const merged = new Map();
      for (const row of rows) {
        const id = String(row?.id ?? '').trim();
        const qty = Number(row?.qty);
        if (!id || !Number.isInteger(qty) || qty < 1) continue;
        merged.set(id, Math.min(99, (merged.get(id) || 0) + qty));
      }
      return [...merged].slice(0, 30).map(([id, qty]) => ({ id, qty }));
    } catch (_) { return []; }
  }

  function saveCart() {
    try { localStorage.setItem(CART_KEY, JSON.stringify(state.cart)); }
    catch (_) { toast('Le panier ne peut pas être conservé sur cet appareil.', true); }
    updateCartCount();
  }

  function updateCartCount() {
    const count = state.cart.reduce((sum, line) => sum + line.qty, 0);
    $('#cartCount').textContent = String(count);
    $('#cartTrigger').setAttribute('aria-label', `Ouvrir le panier, ${count} article${count === 1 ? '' : 's'}`);
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
  }

  function normaliseText(value) {
    return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function safeImageUrl(value) {
    const raw = String(value ?? '').trim();
    if (raw.startsWith('/assets/')) return raw;
    try {
      const url = new URL(raw, window.location.origin);
      if ((url.protocol === 'https:' || url.protocol === 'http:') && url.hostname && !url.username && !url.password) return url.href;
    } catch (_) { /* ignored */ }
    return '';
  }

  function productSlug(product) {
    const slug = String(product?.slug ?? '').toLowerCase();
    if (/^[a-z0-9][a-z0-9-]{0,199}$/.test(slug)) return slug;
    return `article-${encodeURIComponent(String(product?.id ?? '')).replace(/%/g, '-')}`;
  }

  function productHref(product) { return `/produit/${productSlug(product)}/`; }

  function hasPrice(product) {
    if (!product || product.price === null || product.price === undefined || product.price === '') return false;
    const amount = Number(product.price);
    return Number.isFinite(amount) && amount >= 0;
  }

  function money(value) {
    if (value === null || value === undefined || value === '') return 'Prix bientôt disponible';
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount < 0) return 'Prix bientôt disponible';
    return `${new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(amount)} ${esc(state.settings.currency || 'FCFA')}`;
  }

  function isOnSale(product) {
    if (!hasPrice(product)) return false;
    const regular = Number(product.regularPrice);
    const sale = Number(product.salePrice);
    return Boolean(product.onSale) && Number.isFinite(regular) && Number.isFinite(sale) && sale >= 0 && sale < regular;
  }

  function canAddToCart(product) {
    return hasPrice(product) && product?.purchasable !== false && product?.stockStatus !== 'outofstock';
  }

  function productPriceMarkup(product, { multiplier = 1, compact = false } = {}) {
    if (!hasPrice(product)) return '<span class="product-price price-unavailable">Prix bientôt disponible</span>';
    const current = Number(product.price) * multiplier;
    if (isOnSale(product)) {
      const regular = Number(product.regularPrice) * multiplier;
      return `<del class="product-price-regular">${money(regular)}</del><span class="product-price sale-price">${money(current)}</span>${compact ? '' : '<span class="sale-caption">Promotion WooCommerce</span>'}`;
    }
    return `<span class="product-price">${money(current)}</span>`;
  }
  function availabilityClass(product) {
    if (product?.stockStatus === 'outofstock') return 'unavailable';
    if (product?.stockStatus === 'instock' || product?.inStock === true) return 'available';
    return '';
  }
  function availabilityText(product) {
    return String(product?.availability || 'Disponibilité à confirmer');
  }

  async function api(path, options = {}) {
    const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin', ...options });
    let data = {};
    try { data = await response.json(); } catch (_) { /* keep generic error */ }
    if (!response.ok) {
      const error = new Error(data?.error || `La boutique a renvoyé une erreur (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function ensureHomeData({ force = false } = {}) {
    if (state.home && !force && Date.now() - state.homeFetchedAt < 30_000) return state.home;
    const home = await api('/api/store/catalog');
    state.home = home;
    state.homeFetchedAt = Date.now();
    state.settings = { ...state.settings, ...home };
    state.categories = Array.isArray(home.categories) ? home.categories : [];
    updateContactLinks();
    return home;
  }

  function updateContactLinks() {
    const phone = String(state.settings.phone || DEFAULT_PHONE);
    const digits = String(state.settings.whatsapp || phone).replace(/\D/g, '');
    const tel = `tel:${phone.replace(/[^+\d]/g, '')}`;
    $('#topPhone').href = tel;
    $('#topPhone').textContent = phone;
    $('#footerPhone').href = tel;
    $('#footerPhone').textContent = phone;
    $('#footerWhatsapp').href = `https://wa.me/${digits}`;
    const preview = state.settings.backend === 'local-preview';
    $('#footerOrderTitle').textContent = preview ? 'Aperçu local' : 'Paiement WooCommerce';
    $('#footerOrderMessage').textContent = preview
      ? 'Mode aperçu SQLite : aucune commande ni aucun paiement en ligne.'
      : 'Les moyens disponibles sont ceux activés dans la boutique E.S.S.';
    $('#footerPriceMessage').textContent = preview
      ? `${state.settings.currency || 'FCFA'} · Prix de l’aperçu local`
      : `${state.settings.currency || 'FCFA'} · Prix et promotions synchronisés avec WooCommerce`;
    $('#currentYear').textContent = String(new Date().getFullYear());
  }

  function setSeo(title, description) {
    document.title = title;
    const meta = $('meta[name="description"]');
    if (meta) meta.content = description;
    const canonical = $('link[rel="canonical"]');
    if (canonical) canonical.href = `${window.location.origin}${window.location.pathname}`;
  }

  function parseRoute() {
    const path = decodeURIComponent(window.location.pathname).replace(/\/+$/, '') || '/';
    const params = new URLSearchParams(window.location.search);
    const productMatch = path.match(/^\/produit\/([^/]+)$/);
    if (productMatch) return { type: 'product', slug: productMatch[1] };
    if (path === '/catalogue') return { type: 'catalog', params };
    const pages = {
      '/': 'home', '/boutique': 'home', '/a-propos': 'about', '/contact': 'contact',
      '/faq': 'faq', '/livraison-retours': 'delivery', '/confidentialite': 'privacy'
    };
    return { type: pages[path] || 'notfound' };
  }

  function navigate(url, { replace = false, scroll = true } = {}) {
    const target = new URL(url, window.location.origin);
    if (target.origin !== window.location.origin) { window.location.assign(target.href); return; }
    if (replace) window.history.replaceState({}, '', target.pathname + target.search + target.hash);
    else window.history.pushState({}, '', target.pathname + target.search + target.hash);
    closeMenu();
    renderRoute({ scroll });
  }

  function setNav(routeType) {
    $$('[data-nav]').forEach(link => {
      const match = link.dataset.nav === routeType || (routeType === 'product' && link.dataset.nav === 'catalog');
      if (match) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }

  function updateHeaderSearch(value = '') {
    $('#headerSearch').value = value;
  }

  function crumb(items) {
    return `<nav class="breadcrumb" aria-label="Fil d’Ariane">${items.map((item, index) => {
      const last = index === items.length - 1;
      const separator = index ? '<span aria-hidden="true">›</span>' : '';
      return `${separator}${last ? `<span aria-current="page">${esc(item.label)}</span>` : `<a href="${esc(item.href)}" data-route>${esc(item.label)}</a>`}`;
    }).join('')}</nav>`;
  }

  function categoryCard(category) {
    const img = safeImageUrl(category.image);
    const picture = img
      ? `<img src="${esc(img)}" alt="" loading="lazy" decoding="async">`
      : '<span aria-hidden="true">▤</span>';
    return `<a class="category-card" href="/catalogue/?category=${encodeURIComponent(category.id)}" data-route>
      <div class="category-image">${picture}</div><div class="category-card-copy"><strong>${esc(category.name)}</strong><span aria-hidden="true">→</span></div>
    </a>`;
  }

  function productCard(product) {
    const image = safeImageUrl(product?.images?.[0]?.src);
    const href = productHref(product);
    const stockClass = availabilityClass(product);
    const reference = product?.sku ? `Réf. ${esc(product.sku)}` : `Article ${esc(product?.id ?? '')}`;
    const categories = Array.isArray(product?.categories) ? product.categories : [];
    const categoryLabel = categories[0]?.name || 'Catalogue E.S.S.';
    const purchasable = canAddToCart(product);
    const action = purchasable ? 'Ajouter au panier' : !hasPrice(product) ? 'Prix bientôt disponible' : 'Indisponible';
    const tag = isOnSale(product) ? '<span class="product-tag sale-tag">Promotion</span>' : product?.stockStatus === 'outofstock' ? '<span class="product-tag unavailable">Indisponible</span>' : '';
    return `<article class="product-card">
      <a class="product-link" href="${esc(href)}" data-route aria-label="Voir ${esc(product.name)}">
        <div class="product-visual">${image ? `<img src="${esc(image)}" alt="${esc(product.images?.[0]?.alt || product.name)}" loading="lazy" decoding="async">` : '<span class="product-placeholder" aria-hidden="true">▤</span>'}${tag}</div>
        <div class="product-card-body"><div class="product-category">${esc(categoryLabel)}</div><div class="product-reference">${reference}</div><div class="product-name">${esc(product.name)}</div>
          <div class="product-availability ${stockClass}">${esc(availabilityText(product))}</div>
        </div>
      </a>
      <div class="product-card-bottom"><div><span class="product-price-label">Prix WooCommerce</span>${productPriceMarkup(product)}${hasPrice(product) ? '<span class="tax-caption">Prix synchronisé avec la boutique</span>' : ''}</div>
        <button class="add-button" type="button" data-add="${esc(product.id)}" aria-label="${esc(action)} : ${esc(product.name)}"${purchasable ? '' : ' disabled'}>${esc(action)}</button>
      </div>
    </article>`;
  }

  function bindProductActions(root = app) {
    $$('[data-add]', root).forEach(button => {
      // The product tile is a link; keep the action independent from the link navigation.
      const activate = event => {
        event.preventDefault();
        event.stopPropagation();
        const product = findProduct(button.dataset.add);
        if (product) addToCart(product, 1);
      };
      button.addEventListener('click', activate);
    });
  }

  const productCache = new Map();
  function rememberProducts(products) {
    for (const product of products || []) if (product?.id !== undefined) productCache.set(String(product.id), product);
  }
  function findProduct(id) { return productCache.get(String(id)); }

  function productSection(title, description, products, { href = '/catalogue/', label = 'Voir le catalogue' } = {}) {
    const cards = Array.isArray(products) ? products : [];
    return `<section class="section-block" aria-labelledby="${slugId(title)}">
      <div class="section-heading"><div><p class="eyebrow">Sélection E.S.S.</p><h2 id="${slugId(title)}">${esc(title)}</h2><p>${esc(description)}</p></div><a class="section-link" href="${esc(href)}" data-route>${esc(label)} →</a></div>
      ${cards.length ? `<div class="product-grid">${cards.slice(0, 8).map(productCard).join('')}</div>` : '<div class="empty-state"><h3>La sélection arrive</h3><p>Les produits affichés ici sont pilotés depuis la gestion E.S.S.</p></div>'}
    </section>`;
  }

  function slugId(value) { return `section-${normaliseText(value).replace(/[^a-z0-9]+/g, '-')}`; }

  function renderHome() {
    const categories = (state.categories || []).slice().sort((a, b) => (Number(b.count) || 0) - (Number(a.count) || 0)).slice(0, 8);
    const featured = state.home?.featured || [];
    const newest = state.home?.newest || [];
    const popular = state.home?.popular || [];
    const previewMode = state.settings.backend === 'local-preview';
    rememberProducts([...featured, ...newest, ...popular]);
    setSeo('Accueil — Boutique E.S.S.', 'Fournitures de bureau, consommables d’impression et équipements professionnels E.S.S. au Sénégal. Prix synchronisés depuis WooCommerce.');
    app.innerHTML = `<div class="page-shell">
      <section class="hero" aria-labelledby="heroTitle">
        <div class="hero-copy"><p class="eyebrow">${esc(state.settings.brand || 'E.S.S.')} · SÉNÉGAL</p>
          <h1 id="heroTitle">Les essentiels pour faire avancer votre activité.</h1>
          <p>Explorez le catalogue E.S.S. : fournitures de bureau, consommables d’impression et équipements professionnels. Les produits et leurs prix sont synchronisés depuis notre boutique.</p>
          <div class="hero-actions"><a class="button button-primary" href="/catalogue/" data-route>Explorer le catalogue <span aria-hidden="true">→</span></a><a class="hero-phone" href="tel:${esc(state.settings.phone || DEFAULT_PHONE)}">☎ ${esc(state.settings.phone || DEFAULT_PHONE)}</a></div>
          <p class="hero-note">${previewMode ? 'Aperçu du catalogue local SQLite' : 'Prix et promotions synchronisés avec WooCommerce · Paiement sur la boutique E.S.S.'}</p>
        </div>
        <div class="hero-visual" aria-hidden="true"><div class="hero-orb"><div class="hero-logo-card"><img src="/assets/ess-brand-header.jpg" alt="" loading="eager"></div><div class="hero-bubble one">Catalogue actualisé<small>Produits gérés par E.S.S.</small></div><div class="hero-bubble two">Prix WooCommerce<small>Promotions synchronisées</small></div></div></div>
      </section>
      <section class="trust-grid" aria-label="La boutique E.S.S.">
        <article class="trust-card"><span class="trust-icon" aria-hidden="true">↻</span><div><b>Catalogue actualisé</b><small>Les fiches sont gérées dans la boutique E.S.S.</small></div></article>
        <article class="trust-card"><span class="trust-icon" aria-hidden="true">＋</span><div><b>Ajoutez au panier</b><small>Commandez les produits dont le prix est publié.</small></div></article>
        <article class="trust-card"><span class="trust-icon" aria-hidden="true">₣</span><div><b>Paiement WooCommerce</b><small>Choisissez parmi les moyens activés par E.S.S.</small></div></article>
      </section>
      <section class="section-block" aria-labelledby="categoriesTitle"><div class="section-heading"><div><p class="eyebrow">Parcourir</p><h2 id="categoriesTitle">Catégories à découvrir</h2><p>Les familles visibles suivent les catégories publiées dans la boutique E.S.S.</p></div><a class="section-link" href="/catalogue/" data-route>Toutes les catégories →</a></div>
        ${categories.length ? `<div class="category-grid">${categories.map(categoryCard).join('')}</div>` : '<div class="empty-state"><h3>Aucune catégorie publiée</h3><p>Ajoutez ou publiez des catégories dans la gestion de la boutique.</p></div>'}
      </section>
      ${productSection('Produits mis en avant', 'Une sélection définie dans la gestion WooCommerce.', featured)}
      ${productSection('Nouveautés', 'Les dernières fiches produit publiées dans la boutique.', newest)}
      ${productSection('Les plus populaires', 'Les produits les plus consultés ou commandés selon WooCommerce.', popular)}
      <section class="section-block"><div class="feature-band" aria-label="Comment fonctionne la boutique">
        <article><span class="feature-icon" aria-hidden="true">⌕</span><div><h3>Trouvez rapidement</h3><p>Recherchez par désignation, référence et catégorie.</p></div></article>
        <article><span class="feature-icon" aria-hidden="true">▢</span><div><h3>Ajoutez au panier</h3><p>Un panier simple, sans création de compte.</p></div></article>
        <article><span class="feature-icon" aria-hidden="true">₣</span><div><h3>Réglez sur WooCommerce</h3><p>Les moyens de paiement activés s’affichent à l’étape de règlement.</p></div></article>
      </div></section>
      <section class="section-block"><div class="contact-card"><div><p class="eyebrow">Une question ?</p><h2>Besoin d’une précision ?</h2><p>Contactez E.S.S. pour une question sur un produit ou une commande.</p></div><a class="button button-primary" id="homeWhatsapp" href="https://wa.me/${esc(state.settings.whatsapp || '221777477778')}" target="_blank" rel="noopener noreferrer">Écrire sur WhatsApp →</a></div></section>
    </div>`;
    bindProductActions();
  }

  function catalogUrlFromForm(form) {
    const data = new FormData(form);
    const params = new URLSearchParams();
    for (const key of ['q', 'category', 'min_price', 'max_price', 'stock_status', 'orderby', 'order']) {
      const value = String(data.get(key) || '').trim();
      if (value) params.set(key, value);
    }
    params.set('per_page', String(PAGE_SIZE));
    const query = params.toString();
    return `/catalogue/${query ? `?${query}` : ''}`;
  }

  function renderCatalogShell(params) {
    const q = params.get('q') || '';
    const category = params.get('category') || '';
    const min = params.get('min_price') || '';
    const max = params.get('max_price') || '';
    const stock = params.get('stock_status') || '';
    const orderby = params.get('orderby') || 'date';
    const order = params.get('order') || 'desc';
    updateHeaderSearch(q);
    const options = (state.categories || []).map(cat => `<option value="${esc(cat.id)}" ${String(cat.id) === category ? 'selected' : ''}>${esc(cat.name)}</option>`).join('');
    app.innerHTML = `<div class="page-shell">
      ${crumb([{ label: 'Accueil', href: '/' }, { label: 'Catalogue' }])}
      <header class="catalog-intro"><p class="eyebrow">Catalogue E.S.S.</p><h1 class="page-title">Produits & équipements professionnels</h1><p>Recherchez une référence, filtrez par catégorie, tarif et disponibilité. Les informations sont chargées depuis la boutique E.S.S.</p></header>
      <div id="catalogError"></div>
      <div class="catalog-layout">
        <form class="filter-panel" id="catalogFilterForm">
          <h2>Filtrer les produits</h2>
          <div class="filter-group"><label class="group-label" for="filterCategory">Catégorie</label><select class="control" id="filterCategory" name="category"><option value="">Toutes les catégories</option>${options}</select></div>
          <div class="filter-group"><span class="group-label">Prix (${esc(state.settings.currency || 'FCFA')})</span><div class="price-inputs"><label><span class="visually-hidden">Prix minimum</span><input class="control" type="number" name="min_price" min="0" step="1" inputmode="numeric" placeholder="Min" value="${esc(min)}"></label><label><span class="visually-hidden">Prix maximum</span><input class="control" type="number" name="max_price" min="0" step="1" inputmode="numeric" placeholder="Max" value="${esc(max)}"></label></div></div>
          <div class="filter-group"><label class="group-label" for="filterAvailability">Disponibilité</label><select class="control" id="filterAvailability" name="stock_status"><option value="">Tous les statuts</option><option value="instock" ${stock === 'instock' ? 'selected' : ''}>En stock</option><option value="outofstock" ${stock === 'outofstock' ? 'selected' : ''}>Indisponible</option><option value="onbackorder" ${stock === 'onbackorder' ? 'selected' : ''}>À confirmer</option></select></div>
          <input type="hidden" name="q" value="${esc(q)}"><input type="hidden" name="orderby" value="${esc(orderby)}"><input type="hidden" name="order" value="${esc(order)}">
          <div class="filter-buttons"><button class="button button-primary button-small" type="submit">Appliquer les filtres</button><button class="button button-small" type="button" id="clearFilters">Effacer</button></div>
        </form>
        <section class="catalog-results" aria-labelledby="catalogResultTitle"><div class="catalog-toolbar"><span class="catalog-count" id="catalogResultTitle">Chargement du catalogue…</span><label class="catalog-sort">Trier par <select id="catalogSort"><option value="title:asc">Désignation A–Z</option><option value="title:desc">Désignation Z–A</option><option value="price:asc">Prix croissant</option><option value="price:desc">Prix décroissant</option><option value="date:desc">Nouveautés</option><option value="popularity:desc">Popularité</option></select></label></div>
          <div class="product-grid" id="catalogGrid"><div class="skeleton-card"></div><div class="skeleton-card"></div><div class="skeleton-card"></div></div>
          <nav class="pagination" id="catalogPagination" aria-label="Pagination du catalogue"></nav>
        </section>
      </div>
    </div>`;
    $('#catalogSort').value = `${orderby}:${order}`;
    $('#catalogFilterForm').addEventListener('submit', event => { event.preventDefault(); navigate(catalogUrlFromForm(event.currentTarget)); });
    $('#clearFilters').addEventListener('click', () => navigate('/catalogue/'));
    $('#catalogSort').addEventListener('change', event => {
      const [newOrderby, newOrder] = event.target.value.split(':');
      const next = new URL(window.location.href);
      next.searchParams.set('orderby', newOrderby);
      next.searchParams.set('order', newOrder);
      next.searchParams.set('page', '1');
      navigate(next.pathname + next.search, { replace: true, scroll: false });
    });
  }

  function renderPagination(page, totalPages, params) {
    const nav = $('#catalogPagination');
    if (!nav || totalPages <= 1) { if (nav) nav.innerHTML = ''; return; }
    const buildButton = (label, target, disabled = false, current = false) => `<button type="button" data-page="${target}" ${disabled ? 'disabled' : ''} ${current ? 'aria-current="page"' : ''}>${label}</button>`;
    const pages = new Set([1, totalPages, page - 1, page, page + 1].filter(number => number >= 1 && number <= totalPages));
    const ordered = [...pages].sort((a,b) => a-b);
    const buttons = [buildButton('‹', page - 1, page <= 1)];
    let previous = 0;
    for (const number of ordered) {
      if (previous && number - previous > 1) buttons.push('<span aria-hidden="true">…</span>');
      buttons.push(buildButton(String(number), number, false, number === page));
      previous = number;
    }
    buttons.push(buildButton('›', page + 1, page >= totalPages));
    nav.innerHTML = buttons.join('');
    $$('[data-page]', nav).forEach(button => button.addEventListener('click', () => {
      if (button.disabled) return;
      const next = new URL(window.location.href);
      next.searchParams.set('page', button.dataset.page);
      navigate(next.pathname + next.search, { scroll: true });
    }));
  }

  async function loadCatalog(params) {
    const requestId = ++state.catalogRequest;
    const filters = new URLSearchParams(params);
    filters.set('per_page', filters.get('per_page') || String(PAGE_SIZE));
    const page = Math.max(1, Number(filters.get('page') || 1));
    try {
      const result = await api(`/api/store/products?${filters.toString()}`);
      if (requestId !== state.catalogRequest) return;
      const products = Array.isArray(result.products) ? result.products : [];
      rememberProducts(products);
      $('#catalogResultTitle').textContent = `${Number(result.total ?? products.length).toLocaleString('fr-FR')} produit${Number(result.total ?? products.length) > 1 ? 's' : ''}`;
      $('#catalogGrid').innerHTML = products.length ? products.map(productCard).join('') : '<div class="empty-state"><h2>Aucun produit trouvé</h2><p>Modifiez votre recherche ou vos filtres, puis réessayez.</p></div>';
      bindProductActions($('#catalogGrid'));
      renderPagination(page, Number(result.totalPages || 0), params);
      const notice = $('#catalogError'); if (notice) notice.innerHTML = '';
    } catch (error) {
      if (requestId !== state.catalogRequest) return;
      $('#catalogResultTitle').textContent = 'Catalogue indisponible';
      $('#catalogGrid').innerHTML = `<div class="empty-state"><h2>Impossible de charger les produits</h2><p>${esc(error.message)}</p><button class="button button-primary button-small" id="retryCatalog">Réessayer</button></div>`;
      $('#retryCatalog')?.addEventListener('click', () => loadCatalog(params));
    }
  }

  function renderCatalog(params) {
    setSeo('Catalogue — Boutique E.S.S.', 'Parcourez et filtrez les produits, fournitures et équipements professionnels E.S.S.');
    setNav('catalog');
    renderCatalogShell(params);
    loadCatalog(params);
  }

  function renderProductLoading() {
    app.innerHTML = `<div class="page-shell">${crumb([{ label: 'Accueil', href: '/' }, { label: 'Catalogue', href: '/catalogue/' }, { label: 'Chargement' }])}<div class="loading-shell"><div class="loading-line"></div><div class="loading-line short"></div><p>Chargement de la fiche produit…</p></div></div>`;
  }

  function productDetailMarkup(product) {
    const images = (product.images || []).map(image => ({ ...image, src: safeImageUrl(image.src) })).filter(image => image.src);
    const mainImage = images[0]?.src || '';
    const cat = product.categories?.[0]?.name || 'Catalogue E.S.S.';
    const stockClass = availabilityClass(product);
    const summary = product.shortDescription || '';
    const description = product.description || '';
    const reference = product.sku ? `Réf. ${esc(product.sku)}` : `Article ${esc(product.id)}`;
    const purchasable = canAddToCart(product);
    const priceMarkup = !hasPrice(product)
      ? '<div class="detail-price price-unavailable">Prix bientôt disponible</div>'
      : isOnSale(product)
        ? `<div class="detail-prices"><del class="detail-price-regular">${money(product.regularPrice)}</del><div class="detail-price sale-price" itemprop="price">${money(product.price)}</div><span class="sale-caption">Promotion WooCommerce</span></div>`
        : `<div class="detail-price" itemprop="price">${money(product.price)}</div>`;
    const addLabel = purchasable ? 'Ajouter au panier' : !hasPrice(product) ? 'Prix bientôt disponible' : 'Indisponible';
    return `<div class="page-shell">
      ${crumb([{ label: 'Accueil', href: '/' }, { label: 'Catalogue', href: '/catalogue/' }, { label: product.name }])}
      <article class="product-detail" itemscope itemtype="https://schema.org/Product">
        <div class="detail-gallery"><div class="gallery-main">${mainImage ? `<img id="mainProductImage" src="${esc(mainImage)}" alt="${esc(images[0]?.alt || product.name)}" fetchpriority="high">` : '<span class="product-placeholder" aria-hidden="true">▤</span>'}</div>
          ${images.length > 1 ? `<div class="gallery-thumbs" aria-label="Autres photos">${images.map((image, index) => `<button class="gallery-thumb" type="button" data-image-index="${index}" aria-label="Afficher la photo ${index + 1}" aria-pressed="${index === 0}"><img src="${esc(image.src)}" alt="" loading="lazy"></button>`).join('')}</div>` : ''}
        </div>
        <div class="detail-copy"><p class="detail-category">${esc(cat)}</p><h1 itemprop="name">${esc(product.name)}</h1><p class="detail-ref">${reference}</p>
          <div class="detail-price-wrap"><span class="product-price-label">Prix WooCommerce</span>${priceMarkup}${hasPrice(product) ? '<span class="tax-caption">Prix synchronisé avec la boutique</span>' : ''}</div>
          <p class="detail-availability ${stockClass}">${esc(availabilityText(product))}</p>
          ${summary ? `<div class="detail-summary" itemprop="description">${summary}</div>` : ''}
          <div class="detail-actions"><div class="quantity-control" aria-label="Quantité"><button type="button" id="detailQtyDown" aria-label="Diminuer la quantité">−</button><output id="detailQty" aria-live="polite">1</output><button type="button" id="detailQtyUp" aria-label="Augmenter la quantité">＋</button></div><button type="button" class="button button-primary" id="detailAdd" aria-label="${esc(addLabel)} : ${esc(product.name)}"${purchasable ? '' : ' disabled'}>${esc(addLabel)}</button></div>
          <p class="checkout-legal">Vous serez redirigé vers la page de paiement WooCommerce pour choisir un moyen de règlement.</p>
          ${description ? `<section class="detail-description" aria-label="Description complète">${description}</section>` : ''}
        </div>
      </article>
      <section class="similar-section" id="similarProducts"></section>
    </div>`;
  }

  async function loadRelated(product) {
    const holder = $('#similarProducts');
    if (!holder) return;
    let products = [];
    try {
      const ids = (product.relatedIds || []).filter(id => Number(id) > 0).slice(0, 8);
      if (ids.length) {
        const result = await api(`/api/store/products?include=${encodeURIComponent(ids.join(','))}&per_page=8`);
        products = result.products || [];
      }
      if (!products.length && product.categories?.[0]?.id) {
        const result = await api(`/api/store/products?category=${encodeURIComponent(product.categories[0].id)}&per_page=8&orderby=popularity&order=desc`);
        products = (result.products || []).filter(item => String(item.id) !== String(product.id)).slice(0, 4);
      }
    } catch (_) { return; }
    products = products.filter(item => String(item.id) !== String(product.id)).slice(0, 4);
    if (!products.length) return;
    rememberProducts(products);
    holder.innerHTML = `<div class="section-heading"><div><p class="eyebrow">À découvrir</p><h2>Produits similaires</h2></div><a class="section-link" href="/catalogue/" data-route>Voir le catalogue →</a></div><div class="product-grid">${products.map(productCard).join('')}</div>`;
    bindProductActions(holder);
  }

  async function renderProduct(slug) {
    setNav('product');
    renderProductLoading();
    try {
      const product = await api(`/api/store/products/${encodeURIComponent(slug)}`);
      rememberProducts([product]);
      setSeo(`${product.name} — Boutique E.S.S.`, `${product.name}${product.sku ? `, référence ${product.sku}` : ''}. Prix actuel et promotions synchronisés depuis WooCommerce.`);
      app.innerHTML = productDetailMarkup(product);
      const images = (product.images || []).map(image => ({ ...image, src: safeImageUrl(image.src) })).filter(image => image.src);
      const qtyOut = $('#detailQty');
      $('#detailQtyDown')?.addEventListener('click', () => { qtyOut.value = String(Math.max(1, Number(qtyOut.value) - 1)); });
      $('#detailQtyUp')?.addEventListener('click', () => { qtyOut.value = String(Math.min(99, Number(qtyOut.value) + 1)); });
      $$('.gallery-thumb').forEach(button => button.addEventListener('click', () => {
        const image = images[Number(button.dataset.imageIndex)];
        if (!image) return;
        const main = $('#mainProductImage');
        if (main) { main.src = image.src; main.alt = image.alt || product.name; }
        $$('.gallery-thumb').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      }));
      $('#detailAdd')?.addEventListener('click', () => addToCart(product, Number(qtyOut?.value || 1)));
      loadRelated(product);
    } catch (error) {
      setSeo('Produit introuvable — Boutique E.S.S.', 'Cette fiche produit n’est pas disponible. Consultez le catalogue E.S.S.');
      app.innerHTML = `<div class="page-shell">${crumb([{ label: 'Accueil', href: '/' }, { label: 'Catalogue', href: '/catalogue/' }, { label: 'Fiche indisponible' }])}<div class="empty-state"><h2>Cette fiche n’est pas disponible</h2><p>${esc(error.message)}</p><a class="button button-primary button-small" href="/catalogue/" data-route>Retour au catalogue</a></div></div>`;
    }
  }

  const contentPages = {
    about: {
      title: 'À propos de E.S.S.',
      description: 'Découvrez la boutique en ligne E.S.S. et son catalogue professionnel.',
      body: `<div class="content-panel"><h2>Elmansour Supplies & Services</h2><p>E.S.S. propose un catalogue de fournitures de bureau, consommables d’impression et équipements professionnels. Les fiches, prix actuels et promotions affichés sur la boutique sont synchronisés avec WooCommerce.</p><p>Lorsqu’un tarif n’est pas publié dans WooCommerce, la fiche affiche « Prix bientôt disponible » et l’ajout au panier est désactivé. Les commandes sont enregistrées dans WooCommerce et le paiement s’effectue sur sa page de règlement.</p><h3>Une information à vérifier ?</h3><p>Contactez-nous pour une question sur un produit, son conditionnement, une variante ou une compatibilité.</p><a class="button button-primary button-small" href="/contact/" data-route>Contacter E.S.S.</a></div>`
    },
    contact: {
      title: 'Contacter E.S.S.',
      description: 'Contactez E.S.S. par téléphone ou WhatsApp pour une question sur un produit ou une commande.',
      body: () => `<div class="content-panel"><h2>Une question sur un produit ou une commande ?</h2><p>Appelez-nous ou écrivez-nous sur WhatsApp.</p><div class="contact-card"><div><h2>Téléphone / WhatsApp</h2><p>${esc(state.settings.phone || DEFAULT_PHONE)}</p></div><a class="button button-primary" href="https://wa.me/${esc(state.settings.whatsapp || '221777477778')}" target="_blank" rel="noopener noreferrer">Ouvrir WhatsApp →</a></div><p class="checkout-legal">Adresse e-mail, adresse physique et horaires : informations non communiquées. Nous ne les affichons donc pas ici.</p></div>`
    },
    faq: {
      title: 'Questions fréquentes',
      description: 'Réponses sur les produits, la commande et le paiement E.S.S.',
      body: `<div class="content-panel faq-list"><details open><summary>Comment passer une commande ?</summary><p>Ajoutez les produits disponibles au panier, renseignez vos coordonnées puis continuez vers le paiement WooCommerce. La commande apparaît dans la boutique E.S.S.</p></details><details><summary>Comment le paiement est-il effectué ?</summary><p>Après la validation du panier, la page WooCommerce affiche les moyens de paiement configurés et activés par E.S.S. La confirmation finale dépend du résultat renvoyé par le moyen choisi.</p></details><details><summary>Pourquoi un produit affiche-t-il « Prix bientôt disponible » ?</summary><p>Aucun prix actuel n’est publié pour ce produit dans WooCommerce. L’ajout au panier est donc désactivé jusqu’à la saisie d’un prix normal ou promotionnel.</p></details><details><summary>Les prix et promotions sont-ils actualisés ?</summary><p>Oui. Les prix normaux et les prix promotionnels proviennent de WooCommerce et se mettent à jour lorsque la fiche produit est modifiée dans WordPress.</p></details><details><summary>Quels sont les frais et délais de livraison ?</summary><p>Les modalités et tarifs doivent être définis dans les réglages de livraison WooCommerce et dans les informations publiées par E.S.S. Vérifiez-les avant l’ouverture de la boutique.</p></details></div>`
    },
    delivery: {
      title: 'Livraison & retours',
      description: 'Informations sur les réglages de livraison et les retours E.S.S.',
      body: `<div class="content-panel"><h2>Livraison ou retrait</h2><p>Les zones, modes, frais et délais de livraison doivent être configurés dans WooCommerce selon les conditions réelles d’E.S.S. Aucune adresse, zone ou grille tarifaire n’est inventée sur cette page.</p><h3>Retours</h3><p>Les modalités de retour ou d’échange n’ont pas été communiquées. Contactez E.S.S. pour obtenir les conditions applicables avant l’achat.</p><a class="button button-primary button-small" href="/contact/" data-route>Contacter E.S.S.</a></div>`
    },
    privacy: {
      title: 'Confidentialité',
      description: 'Informations sur les données transmises lors d’une commande E.S.S.',
      body: `<div class="content-panel"><h2>Informations transmises</h2><p>Le checkout WooCommerce collecte les renseignements nécessaires à la commande selon les champs configurés dans la boutique. Ces données sont transmises à WooCommerce pour enregistrer et traiter votre achat.</p><p>Le paiement s’effectue sur la page WooCommerce et auprès du moyen de paiement choisi. Ne saisissez pas vos données de carte ou de paiement sur la vitrine E.S.S.</p><h3>Question ou demande liée à vos informations</h3><p>Contactez E.S.S. au ${esc(state.settings.phone || DEFAULT_PHONE)}. Cette page présente une information de base et ne remplace pas une politique de confidentialité juridique validée pour le pays d’exploitation.</p></div>`
    }
  };

  function renderContentPage(type) {
    const page = contentPages[type];
    if (!page) {
      setSeo('Page introuvable — Boutique E.S.S.', 'Cette page n’existe pas.');
      app.innerHTML = `<div class="page-shell content-page"><div class="empty-state"><h2>Page introuvable</h2><p>Le lien demandé n’existe pas.</p><a href="/" data-route class="button button-primary button-small">Retour à l’accueil</a></div></div>`;
      return;
    }
    setSeo(`${page.title} — E.S.S.`, page.description);
    app.innerHTML = `<div class="page-shell content-page">${crumb([{ label: 'Accueil', href: '/' }, { label: page.title }])}<p class="eyebrow">E.S.S. · Informations</p><h1 class="page-title">${esc(page.title)}</h1><p class="content-lead">${esc(page.description)}</p>${typeof page.body === 'function' ? page.body() : page.body}</div>`;
  }

  async function renderRoute({ scroll = true } = {}) {
    const route = parseRoute();
    setNav(route.type);
    $('#app').setAttribute('aria-busy', 'true');
    try {
      if (route.type === 'home') {
        if (!state.home) {
          app.innerHTML = `<div class="page-shell loading-shell"><div class="loading-line"></div><div class="loading-line short"></div><p>Chargement du catalogue E.S.S.…</p></div>`;
          await ensureHomeData();
        }
        renderHome();
      } else if (route.type === 'catalog') {
        if (!state.home) await ensureHomeData();
        renderCatalog(route.params);
      } else if (route.type === 'product') {
        if (!state.home) await ensureHomeData();
        await renderProduct(route.slug);
      } else if (route.type === 'notfound') {
        renderContentPage('notfound');
      } else {
        if (!state.home) await ensureHomeData().catch(() => null);
        renderContentPage(route.type);
      }
    } catch (error) {
      setSeo('Boutique E.S.S. — Catalogue indisponible', 'La connexion au catalogue E.S.S. est momentanément indisponible.');
      app.innerHTML = `<div class="page-shell content-page"><div class="empty-state"><h2>Impossible de charger la boutique</h2><p>${esc(error.message || 'Vérifiez la connexion à la boutique E.S.S.')}</p><button class="button button-primary button-small" id="retryHome">Réessayer</button></div></div>`;
      $('#retryHome')?.addEventListener('click', async () => { state.home = null; await renderRoute({ scroll: false }); });
    } finally {
      $('#app').setAttribute('aria-busy', 'false');
      if (scroll) window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  function toast(message, isError = false) {
    const region = $('#toastRegion');
    const node = document.createElement('div');
    node.className = `toast${isError ? ' error' : ''}`;
    node.setAttribute('role', isError ? 'alert' : 'status');
    node.textContent = message;
    region.append(node);
    window.setTimeout(() => node.remove(), 3500);
  }

  function addToCart(product, quantity = 1) {
    if (!product || product.id === undefined) return;
    if (!hasPrice(product)) { toast('Prix bientôt disponible', true); return; }
    if (!canAddToCart(product)) { toast('Ce produit est indisponible à l’achat.', true); return; }
    const id = String(product.id);
    const qty = Math.max(1, Math.min(99, Number(quantity) || 1));
    const existing = state.cart.find(line => line.id === id);
    if (existing) existing.qty = Math.min(99, existing.qty + qty);
    else if (state.cart.length < 30) state.cart.push({ id, qty });
    else { toast('Le panier ne peut pas dépasser 30 références.', true); return; }
    rememberProducts([product]);
    saveCart();
    toast('Article ajouté au panier.');
    openCart();
  }

  function cartSummaryMarkup(products) {
    if (!products.length) return '<div class="cart-empty"><span class="cart-empty-icon" aria-hidden="true">▢</span>Votre panier est vide.<br>Ajoutez des produits depuis le catalogue.</div>';
    const purchasableLines = products.filter(line => canAddToCart(line.product));
    const unavailableLines = products.filter(line => !canAddToCart(line.product));
    const subtotal = purchasableLines.reduce((sum, line) => sum + Number(line.product.price) * line.qty, 0);
    const summary = purchasableLines.length
      ? `<div class="cart-summary"><span>Sous-total des produits</span><strong>${money(subtotal)}</strong></div>`
      : '';
    const preview = state.settings.backend === 'local-preview';
    const note = preview
      ? '<div class="cart-note">Aperçu local : aucune commande ni aucun paiement WooCommerce ne sera effectué ici.</div>'
      : '<div class="cart-note">La commande sera enregistrée dans WooCommerce. Vous choisirez un moyen de paiement sur la page de règlement.</div>';
    const unavailableNote = unavailableLines.length
      ? '<div class="cart-note">Un article n’est plus achetable. Retirez-le du panier pour continuer.</div>'
      : '';
    const items = products.map(({ product, qty }) => {
      const unit = hasPrice(product) ? `${productPriceMarkup(product, { compact: true })} / unité` : 'Prix bientôt disponible';
      const linePrice = hasPrice(product) ? productPriceMarkup(product, { multiplier: qty, compact: true }) : '<span class="product-price price-unavailable">Prix bientôt disponible</span>';
      return `<div class="cart-line"><div class="cart-line-info"><span class="cart-line-name">${esc(product.name)}</span><span class="cart-line-sub">${product.sku ? `Réf. ${esc(product.sku)} · ` : ''}${unit}</span><div class="cart-line-controls"><button type="button" data-qty="${esc(product.id)}" data-delta="-1" aria-label="Diminuer ${esc(product.name)}">−</button><output>${qty}</output><button type="button" data-qty="${esc(product.id)}" data-delta="1" aria-label="Augmenter ${esc(product.name)}">＋</button><button type="button" class="remove-item" data-remove="${esc(product.id)}">Retirer</button></div></div><div class="cart-line-price">${linePrice}</div></div>`;
    }).join('');
    return `<div>${items}</div>${summary}${unavailableNote}${note}${checkoutFormMarkup({ disabled: !purchasableLines.length || unavailableLines.length })}`;
  }

  function checkoutFormMarkup({ disabled = false } = {}) {
    const preview = state.settings.backend === 'local-preview';
    const action = preview ? 'Continuer en aperçu local' : 'Continuer vers WooCommerce';
    const legal = preview
      ? 'Mode aperçu : aucun paiement réel n’est disponible tant que la boutique WooCommerce n’est pas configurée.'
      : 'Vous renseignerez vos coordonnées, choisirez livraison ou retrait et paierez sur le checkout natif WooCommerce.';
    return `<div class="checkout-form">
      <button class="checkout-button" id="submitOrder" type="button"${disabled ? ' disabled' : ''}>${action}</button>
      <p class="checkout-legal">${legal}</p>
    </div>`;
  }

  async function hydrateCart() {
    if (!state.cart.length) return [];
    const ids = state.cart.map(line => line.id);
    const query = new URLSearchParams({ include: ids.join(','), per_page: '48' });
    const result = await api(`/api/store/products?${query.toString()}`);
    rememberProducts(result.products || []);
    return state.cart.map(line => ({ ...line, product: findProduct(line.id) })).filter(line => line.product);
  }

  async function openCart() {
    state.lastFocus = document.activeElement;
    $('#drawerBackdrop').hidden = false;
    $('#cartPanel').inert = false;
    $('#cartPanel').setAttribute('aria-hidden', 'false');
    $('#cartPanel').classList.add('open');
    document.body.style.overflow = 'hidden';
    renderCartLoading();
    $('#drawerClose').focus();
    try {
      const products = await hydrateCart();
      renderCart(products);
    } catch (error) {
      $('#drawerContent').innerHTML = `<div class="empty-state"><h3>Impossible d’actualiser le panier</h3><p>${esc(error.message)}</p><button class="button button-primary button-small" id="retryCart">Réessayer</button></div>`;
      $('#retryCart')?.addEventListener('click', openCart);
    }
  }

  function renderCartLoading() {
    $('#drawerContent').innerHTML = '<div class="loading-shell"><div class="loading-line"></div><p>Actualisation des produits et prix…</p></div>';
  }

  function renderCart(products) {
    const validIds = new Set(products.map(line => String(line.product.id)));
    if (state.cart.some(line => !validIds.has(line.id))) {
      state.cart = state.cart.filter(line => validIds.has(line.id));
      saveCart();
      toast('Un article retiré de la boutique a été enlevé du panier.', true);
    }
    const preview = state.settings.backend === 'local-preview';
    $('#drawerSubtitle').textContent = preview
      ? 'Aperçu local du panier — aucun paiement réel.'
      : 'Vérifiez votre panier puis poursuivez vers le paiement WooCommerce.';
    $('#drawerContent').innerHTML = cartSummaryMarkup(products);
    $$('[data-qty]', $('#drawerContent')).forEach(button => button.addEventListener('click', () => changeQuantity(button.dataset.qty, Number(button.dataset.delta))));
    $$('[data-remove]', $('#drawerContent')).forEach(button => button.addEventListener('click', () => removeFromCart(button.dataset.remove)));
    $('#submitOrder')?.addEventListener('click', submitOrder);
  }

  function changeQuantity(id, delta) {
    const line = state.cart.find(item => item.id === String(id));
    if (!line) return;
    line.qty = Math.max(0, Math.min(99, line.qty + delta));
    if (line.qty === 0) state.cart = state.cart.filter(item => item.id !== String(id));
    saveCart();
    openCart();
  }

  function removeFromCart(id) {
    state.cart = state.cart.filter(line => line.id !== String(id));
    saveCart();
    openCart();
  }

  function closeCart() {
    $('#drawerBackdrop').hidden = true;
    $('#cartPanel').classList.remove('open');
    $('#cartPanel').setAttribute('aria-hidden', 'true');
    $('#cartPanel').inert = true;
    document.body.style.overflow = '';
    if (state.lastFocus?.focus) state.lastFocus.focus();
  }

  async function submitOrder(event) {
    event.preventDefault();
    if (state.sending) return;
    const button = event.currentTarget;
    if (state.settings.backend === 'local-preview') {
      toast('Le paiement est disponible uniquement après configuration de WooCommerce.', true);
      return;
    }
    const lines = await hydrateCart().catch(error => { toast(error.message, true); return null; });
    if (!lines?.length) { toast('Votre panier est vide ou indisponible.', true); return; }
    if (lines.some(line => !canAddToCart(line.product))) {
      toast('Retirez les produits non achetables avant de continuer.', true);
      renderCart(lines);
      return;
    }
    state.sending = true;
    button.disabled = true;
    button.textContent = 'Préparation du panier…';
    try {
      const checkout = await api('/api/store/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: lines.map(line => ({ id: line.id, qty: line.qty })) })
      });
      if (checkout.preview === true) {
        state.sending = false;
        toast('L’aperçu local ne traite pas les commandes ni les paiements.', true);
        button.disabled = false;
        button.textContent = 'Continuer en aperçu local';
        return;
      }
      const action = new URL(String(checkout.checkoutAction || ''));
      const token = String(checkout.checkoutToken || '');
      if (action.protocol !== 'https:' || !/\/wp-admin\/admin-post\.php$/.test(action.pathname) || !token) {
        throw new Error('La redirection vers le checkout WooCommerce n’est pas configurée.');
      }
      const handoff = document.createElement('form');
      handoff.method = 'POST';
      handoff.action = action.href;
      handoff.hidden = true;
      const fields = { action: 'ess_storefront_checkout', token };
      for (const [name, value] of Object.entries(fields)) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        input.value = value;
        handoff.append(input);
      }
      document.body.append(handoff);
      state.cart = [];
      saveCart();
      button.textContent = 'Redirection vers WooCommerce…';
      state.sending = false;
      handoff.submit();
    } catch (error) {
      state.sending = false;
      if ($('#submitOrder')) {
        $('#submitOrder').disabled = false;
        $('#submitOrder').textContent = 'Continuer vers WooCommerce';
      }
      toast(error.message || 'Impossible d’ouvrir le checkout WooCommerce. Réessayez.', true);
    }
  }

  async function refreshCurrentView() {
    if (document.hidden) return;
    const route = parseRoute();
    if (route.type !== 'home' && route.type !== 'catalog') return;
    try {
      await ensureHomeData({ force: true });
      if (route.type === 'home') renderHome();
      else loadCatalog(route.params);
    } catch (_) { /* Keep the last valid page visible during a short WordPress outage. */ }
  }

  function bindGlobalEvents() {
    $('#headerSearchForm').addEventListener('submit', event => {
      event.preventDefault();
      const query = $('#headerSearch').value.trim();
      navigate(`/catalogue/${query ? `?q=${encodeURIComponent(query)}` : ''}`);
    });
    $('#cartTrigger').addEventListener('click', openCart);
    $('#drawerClose').addEventListener('click', closeCart);
    $('#drawerBackdrop').addEventListener('click', closeCart);
    $('#menuToggle').addEventListener('click', () => {
      const open = $('#mainNav').classList.toggle('open');
      $('#menuToggle').setAttribute('aria-expanded', String(open));
      $('#menuToggle').setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
    });
    document.addEventListener('click', event => {
      const anchor = event.target.closest('a[data-route]');
      if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = new URL(anchor.href, window.location.origin);
      if (target.origin !== window.location.origin) return;
      event.preventDefault();
      navigate(target.pathname + target.search + target.hash);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        if ($('#cartPanel').classList.contains('open')) closeCart();
        else closeMenu();
      }
      if (event.key === 'Tab' && $('#cartPanel').classList.contains('open')) {
        const focusable = $$('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', $('#cartPanel'))
          .filter(element => !element.closest('[hidden]') && element.offsetParent !== null);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); $('#headerSearch').focus();
      }
    });
    window.addEventListener('popstate', () => { closeMenu(); renderRoute({ scroll: true }); });
  }

  function closeMenu() {
    $('#mainNav').classList.remove('open');
    $('#menuToggle').setAttribute('aria-expanded', 'false');
    $('#menuToggle').setAttribute('aria-label', 'Ouvrir le menu');
  }

  async function init() {
    updateContactLinks();
    updateCartCount();
    bindGlobalEvents();
    $('#cartPanel').inert = true;
    window.setInterval(refreshCurrentView, 60_000);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && Date.now() - state.homeFetchedAt > 60_000) refreshCurrentView();
    });
    await renderRoute({ scroll: false });
  }

  init();
})();
