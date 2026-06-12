"""M1 — Real site audit: PageSpeed Insights + HTML analysis → TicketResponse."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Dict, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from models import AuditInput, Prioridad, Ticket, TicketResponse, TicketSummary
from ticket_engine import generate_tickets

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
HTML_TIMEOUT = 20.0
PSI_TIMEOUT  = 35.0
UA = "Mozilla/5.0 (compatible; WPRecover/2.0)"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _fetch_psi(url: str) -> dict:
    params = {"url": url, "strategy": "mobile"}
    async with httpx.AsyncClient(timeout=PSI_TIMEOUT, follow_redirects=True) as c:
        r = await c.get(PSI_ENDPOINT, params=params)
        r.raise_for_status()
        return r.json()


async def _fetch_html(url: str) -> Tuple[str, dict, int]:
    """Returns (html_text, response_headers_lower, status_code)."""
    # Cache-bust: append a unique query param so CDN/page-cache layers
    # (Cloudflare, WP Rocket, etc.) don't serve a stale snapshot, and ask
    # any intermediary not to cache either.
    parts = urlsplit(url)
    query = parse_qsl(parts.query)
    query.append(("_cb", str(int(time.time() * 1000))))
    bust_url = urlunsplit(parts._replace(query=urlencode(query)))

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "es,en;q=0.9",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    }
    async with httpx.AsyncClient(timeout=HTML_TIMEOUT, follow_redirects=True) as c:
        r = await c.get(bust_url, headers=headers)
        return r.text, {k.lower(): v.lower() for k, v in r.headers.items()}, r.status_code

# ---------------------------------------------------------------------------
# SEO checks (9)
# ---------------------------------------------------------------------------

def _seo_checks(html: str, psi: dict) -> Dict[str, bool]:
    lh_audits = psi.get("lighthouseResult", {}).get("audits", {})

    title = bool(re.search(r'<title[^>]*>[^<]{3,}</title>', html, re.I))

    meta_desc = bool(
        re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'][^"\']{15,}', html, re.I) or
        re.search(r'<meta[^>]+content=["\'][^"\']{15,}["\'][^>]+name=["\']description["\']', html, re.I)
    )

    canonical = bool(re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']https?://', html, re.I))

    og_image = bool(
        re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']https?://[^"\']{5,}', html, re.I) or
        re.search(r'<meta[^>]+content=["\']https?://[^"\']+\.(jpg|jpeg|png|webp)["\'][^>]+property=["\']og:image["\']', html, re.I)
    )

    schema = bool(
        re.search(r'type=["\']application/ld\+json["\']', html, re.I) or
        re.search(r'itemtype=["\']https?://schema\.org/', html, re.I)
    )

    sitemap_html = bool(
        re.search(r'<link[^>]+rel=["\'][^"\']*sitemap["\']', html, re.I) or
        re.search(r'sitemap\.xml', html, re.I)
    )
    # PSI also checks robots.txt which usually declares sitemap
    sitemap_psi_score = lh_audits.get("robots-txt", {}).get("score")
    sitemap = sitemap_html or (sitemap_psi_score is not None and float(sitemap_psi_score) > 0.49)

    noindex = bool(
        re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', html, re.I) or
        re.search(r'<meta[^>]+content=["\'][^"\']*noindex[^"\']*["\'][^>]+name=["\']robots["\']', html, re.I)
    )

    h1_list = re.findall(r'<h1[^>]*>.*?</h1>', html, re.I | re.S)
    h1_ok = len(h1_list) == 1

    total_imgs = len(re.findall(r'<img\b', html, re.I))
    imgs_with_alt = len(re.findall(r'<img[^>]+alt=["\'][^"\']+["\']', html, re.I))
    alt_imgs_ok = total_imgs == 0 or (imgs_with_alt / total_imgs >= 0.8)

    return {
        "title":     title,
        "meta_desc": meta_desc,
        "canonical": canonical,
        "og_image":  og_image,
        "schema":    schema,
        "sitemap":   sitemap,
        "robots":    not noindex,
        "h1":        h1_ok,
        "alt_imgs":  alt_imgs_ok,
    }

# ---------------------------------------------------------------------------
# Performance checks (7) — all from PSI
# ---------------------------------------------------------------------------

def _perf_checks(psi: dict) -> Dict[str, bool]:
    audits = psi.get("lighthouseResult", {}).get("audits", {})

    def numeric(key: str, threshold: float, default: bool = True) -> bool:
        v = audits.get(key, {}).get("numericValue")
        return bool(float(v) <= threshold) if v is not None else default

    def score(key: str, threshold: float = 0.49, default: bool = True) -> bool:
        s = audits.get(key, {}).get("score")
        return bool(float(s) > threshold) if s is not None else default

    webp = score("modern-image-formats") or score("uses-webp-images")

    return {
        "LCP":       numeric("largest-contentful-paint", 2500),
        "CLS":       numeric("cumulative-layout-shift", 0.10),
        "INP":       numeric("interaction-to-next-paint", 200, default=True),
        "cache":     score("uses-long-cache-ttl"),
        "gzip":      score("uses-text-compression"),
        "webp":      webp,
        "lazy_load": score("offscreen-images"),
    }

# ---------------------------------------------------------------------------
# Conversion checks (5)
# ---------------------------------------------------------------------------

def _conv_checks(html: str) -> Dict[str, bool]:
    tel = bool(re.search(r'href=["\']tel:[+\d\s\-\(\)]{5,}["\']', html, re.I))

    whatsapp = bool(re.search(r'wa\.me/|api\.whatsapp\.com/send|whatsapp\.com/send', html, re.I))

    forms = bool(re.search(r'<form\b[^>]*>', html, re.I))

    cta_words = (
        r'contact[ao]?|consult[ao]?|compra|buy|reserva|cotiza|llama|call|started|'
        r'free|gratis|demo|prueba|solicita|pedir|oferta|descuento|suscri'
    )
    cta = bool(
        re.search(r'<(button|a)[^>]*>\s*[^<]*(' + cta_words + r')[^<]*', html, re.I) or
        re.search(r'class=["\'][^"\']*\b(cta|btn-primary|btn-cta|action)[^"\']*["\']', html, re.I) or
        re.search(r'href=["\'][^"\']*#?(contact|cotiza|consult|solicita)', html, re.I)
    )

    tracking = bool(re.search(
        r'gtag\s*\(|googletagmanager\.com|fbq\s*\(|analytics\.js|clarity\.ms|hotjar\.|_gaq\b',
        html, re.I
    ))

    return {
        "tel_clickeable": tel,
        "whatsapp":       whatsapp,
        "formularios":    forms,
        "CTA":            cta,
        "tracking":       tracking,
    }

# ---------------------------------------------------------------------------
# Security checks (5)
# ---------------------------------------------------------------------------

def _sec_checks(html: str, url: str, resp_headers: dict) -> Dict[str, bool]:
    ssl = url.lower().startswith("https://")

    # meta_generator exposing WP version → bad
    meta_gen = re.search(
        r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']WordPress\s+[\d\.]+',
        html, re.I
    )
    meta_generator_ok = meta_gen is None

    # WP version exposed via generator tag or version query params in asset URLs
    wp_version_exposed = bool(
        meta_gen or
        len(re.findall(r'\?ver=[\d\.]{3,}', html, re.I)) > 5  # many versioned asset URLs
    )
    wp_version_ok = not wp_version_exposed

    # HTTP security headers
    has_xfo  = "x-frame-options" in resp_headers
    has_csp  = "content-security-policy" in resp_headers
    has_hsts = "strict-transport-security" in resp_headers
    has_xcto = "x-content-type-options" in resp_headers
    headers_ok = sum([has_xfo, has_csp, has_hsts, has_xcto]) >= 2

    return {
        "ssl":            ssl,
        "meta_generator": meta_generator_ok,
        "wp_version":     wp_version_ok,
        "headers":        headers_ok,
        "plugins_desact": True,  # not detectable from a single HTML page
    }

# ---------------------------------------------------------------------------
# WooCommerce checks (5)
# ---------------------------------------------------------------------------

def _woo_checks(html: str) -> Dict[str, bool]:
    is_woo = bool(re.search(
        r'woocommerce|class=["\'][^"\']*\bwc-|wc_add_to_cart|add_to_cart_url',
        html, re.I
    ))

    if not is_woo:
        return {k: True for k in
                ["productos_sin_cat", "productos_sin_img", "slugs_dup", "precios", "pasarelas"]}

    sin_cat  = bool(re.search(r'/product-category/uncategorized', html, re.I))
    sin_img  = bool(re.search(r'woocommerce-placeholder|woocommerce-product-gallery__image--placeholder', html, re.I))
    precios  = bool(re.search(r'woocommerce-Price-amount|class=["\'][^"\']*\bprice\b', html, re.I))
    pasarelas = bool(re.search(
        r'payment.method|paypal|stripe|mercadopago|webpay|transbank|getnet|khipu',
        html, re.I
    ))

    return {
        "productos_sin_cat": not sin_cat,
        "productos_sin_img": not sin_img,
        "slugs_dup":         True,
        "precios":           precios,
        "pasarelas":         pasarelas,
    }

# ---------------------------------------------------------------------------
# Score calculator — mirrors M5 formula
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "SEO":         0.30,
    "Performance": 0.20,
    "Conversion":  0.20,
    "Seguridad":   0.15,
    "WooCommerce": 0.15,
}


def _calc_score(checks: Dict[str, Dict[str, bool]]) -> float:
    score = 0.0
    for cat, w in _WEIGHTS.items():
        cat_checks = checks.get(cat, {})
        if not cat_checks:
            continue
        passed = sum(1 for v in cat_checks.values() if v)
        score += w * (passed / len(cat_checks)) * 100
    return round(score, 1)

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_full_audit(url: str) -> TicketResponse:
    if not url.lower().startswith("http"):
        url = "https://" + url

    psi_task  = asyncio.create_task(_fetch_psi(url))
    html_task = asyncio.create_task(_fetch_html(url))

    psi_result, html_result = await asyncio.gather(
        psi_task, html_task, return_exceptions=True
    )

    psi_ok:  bool  = isinstance(psi_result, dict) and bool(psi_result)
    html_ok: bool  = isinstance(html_result, tuple)

    psi: dict = psi_result if psi_ok else {}

    if html_ok:
        html_text, resp_headers, status_code = html_result  # type: ignore[misc]
    else:
        html_text, resp_headers, status_code = "", {}, 0

    # When HTML fetch was blocked/failed but PSI succeeded the site is reachable
    # — use all-pass defaults for HTML-only checks instead of false-positive failures.
    html_available = html_ok and bool(html_text)

    _html   = html_text if html_available else ""
    _ssl_url = url  # SSL check always uses the URL scheme, not HTML content

    checks: Dict[str, Dict[str, bool]] = {
        "SEO":         _seo_checks(_html, psi) if html_available else {k: True for k in
                       ["title","meta_desc","canonical","og_image","schema","sitemap","robots","h1","alt_imgs"]},
        "Performance": _perf_checks(psi),
        "Conversion":  _conv_checks(_html) if html_available else {k: True for k in
                       ["tel_clickeable","whatsapp","formularios","CTA","tracking"]},
        "Seguridad":   _sec_checks(_html, _ssl_url, resp_headers),
        "WooCommerce": _woo_checks(_html),
    }

    errores: list[str] = []
    if html_ok:
        if status_code >= 500:
            errores.append("error_500")
    elif not psi_ok:
        # Both fetches failed → site is genuinely unreachable
        errores.append("sitio_caido")

    audit = AuditInput(
        checks=checks,
        errores=errores,
        recovery_score=_calc_score(checks),
        url=url,
    )

    tickets: list[Ticket] = generate_tickets(audit)

    summary = TicketSummary(
        total=len(tickets),
        criticos=sum(1 for t in tickets if t.prioridad == Prioridad.Critica),
        altos=sum(1 for t in tickets if t.prioridad == Prioridad.Alta),
        medios=sum(1 for t in tickets if t.prioridad == Prioridad.Media),
        bajos=sum(1 for t in tickets if t.prioridad == Prioridad.Baja),
        estimacion_total_min=sum(t.estimacion for t in tickets),
    )

    return TicketResponse(
        url=url,
        recovery_score=audit.recovery_score,
        resumen=summary,
        tickets=tickets,
    )
