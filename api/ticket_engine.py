from __future__ import annotations

from typing import Dict, List, Tuple

from models import AuditInput, Categoria, EstadoTicket, Prioridad, Ticket

# ---------------------------------------------------------------------------
# Static knowledge base derived from wprecover.modules.json (M2)
# ---------------------------------------------------------------------------

PRIORITY_ORDER: Dict[str, int] = {
    Prioridad.Critica: 0,
    Prioridad.Alta: 1,
    Prioridad.Media: 2,
    Prioridad.Baja: 3,
}

AGENT_MAP: Dict[str, str] = {
    Categoria.SEO: "SEOAgent",
    Categoria.Performance: "PerfAgent",
    Categoria.Conversion: "CROAgent",
    Categoria.Seguridad: "SecAgent",
    Categoria.WooCommerce: "WooAgent",
}

# check_name -> (titulo, prioridad, impacto, estimacion_min)
CHECK_CONFIG: Dict[str, Dict[str, Tuple[str, Prioridad, str, int]]] = {
    Categoria.SEO: {
        "title":      ("Falta título SEO",                         Prioridad.Alta,  "Pérdida directa de posicionamiento en Google",           15),
        "meta_desc":  ("Falta meta descripción",                   Prioridad.Alta,  "CTR reducido en resultados de búsqueda",                  15),
        "canonical":  ("Canonical tag ausente o incorrecto",       Prioridad.Alta,  "Contenido duplicado penalizado por Google",               20),
        "og_image":   ("Falta imagen Open Graph",                  Prioridad.Baja,  "Baja visibilidad al compartir en redes sociales",         20),
        "schema":     ("Schema markup ausente",                    Prioridad.Baja,  "Sin rich snippets en resultados de Google",               30),
        "sitemap":    ("Sitemap XML no encontrado o inválido",     Prioridad.Alta,  "Indexación incompleta de páginas",                        20),
        "robots":     ("robots.txt mal configurado",               Prioridad.Alta,  "Riesgo de bloquear indexación completa del sitio",        15),
        "h1":         ("H1 ausente o duplicado",                   Prioridad.Alta,  "Señal SEO on-page débil, confunde a Googlebot",           15),
        "alt_imgs":   ("Imágenes sin atributo ALT",                Prioridad.Baja,  "Accesibilidad y SEO de imágenes reducidos",               30),
    },
    Categoria.Performance: {
        "LCP":       ("LCP superior a 2.5s",                       Prioridad.Media, "Core Web Vital crítico — penalización directa en ranking", 60),
        "CLS":       ("CLS superior a 0.1",                        Prioridad.Media, "Experiencia visual degradada, posible penalización",        45),
        "INP":       ("INP superior a 200ms",                      Prioridad.Media, "Interactividad lenta penaliza ranking en Google",           60),
        "cache":     ("Cache del navegador no configurado",        Prioridad.Media, "Cargas lentas en visitas repetidas",                        30),
        "gzip":      ("Compresión GZIP deshabilitada",             Prioridad.Media, "Transferencia de datos innecesariamente alta",              20),
        "webp":      ("Imágenes sin formato WebP",                 Prioridad.Media, "Tamaño de imágenes no optimizado, carga lenta",             45),
        "lazy_load": ("Lazy load no implementado",                 Prioridad.Media, "Carga inicial del sitio más lenta de lo necesario",         30),
    },
    Categoria.Conversion: {
        "tel_clickeable": ("Teléfono no clickeable en móvil",     Prioridad.Alta, "Pérdida de llamadas desde dispositivos móviles",             20),
        "whatsapp":       ("Botón WhatsApp ausente",              Prioridad.Alta, "Canal de contacto clave sin activar",                        25),
        "formularios":    ("Formularios de contacto sin funcionar",Prioridad.Alta, "Leads perdidos directamente — impacto en ventas",           45),
        "CTA":            ("Call-to-action ausente o poco visible",Prioridad.Alta, "Tasa de conversión reducida significativamente",             30),
        "tracking":       ("Analytics/tracking no configurado",   Prioridad.Alta, "Sin datos para tomar decisiones de optimización",            30),
    },
    Categoria.Seguridad: {
        "wp_version":      ("Versión de WordPress expuesta u obsoleta",  Prioridad.Alta, "Vulnerabilidades de seguridad conocidas y explotables",  30),
        "plugins_desact":  ("Plugins inactivos instalados",              Prioridad.Alta, "Vector de ataque innecesario activo",                     20),
        "meta_generator":  ("Meta generator expone versión de WP",      Prioridad.Alta, "Información sensible pública facilita ataques dirigidos", 15),
        "headers":         ("Headers de seguridad HTTP ausentes",        Prioridad.Alta, "Vulnerabilidades XSS, clickjacking y sniffing",           30),
        "ssl":             ("SSL/HTTPS no configurado o inválido",       Prioridad.Alta, "Sitio inseguro — penalización Google + pérdida de confianza", 45),
    },
    Categoria.WooCommerce: {
        "productos_sin_cat": ("Productos sin categoría asignada",  Prioridad.Media, "Navegación y SEO de tienda afectados",                    30),
        "productos_sin_img": ("Productos sin imagen",              Prioridad.Alta,  "Tasa de conversión en tienda reducida directamente",       45),
        "slugs_dup":         ("Slugs de productos duplicados",     Prioridad.Alta,  "Errores de indexación y contenido duplicado",              30),
        "precios":           ("Productos sin precio configurado",  Prioridad.Alta,  "Ventas bloqueadas — clientes no pueden comprar",           20),
        "pasarelas":         ("Pasarela de pago no configurada",   Prioridad.Alta,  "Imposible completar compras en la tienda",                 60),
    },
}

# Critical site errors -> (titulo, categoria, impacto, estimacion_min)
ERROR_CONFIG: Dict[str, Tuple[str, Categoria, str, int]] = {
    "sitio_caido":    ("Sitio completamente caído",               Categoria.Seguridad,    "100% de tráfico y ventas perdidas",                  120),
    "error_500":      ("Error 500 — Server Error crítico",        Categoria.Seguridad,    "Sitio inaccesible, pérdida total de visitas activas", 90),
    "checkout_roto":  ("Checkout de WooCommerce no funciona",     Categoria.WooCommerce,  "Ventas completamente bloqueadas",                    120),
}

# Tickets that must be resolved before others can start
DEPENDENCY_RULES: Dict[str, List[str]] = {
    # Performance improvements only make sense once security/SSL is solid
    "Performance": ["Seguridad"],
    # WooCommerce checkout depends on SSL
    "WooCommerce": ["Seguridad"],
}


def _ticket_id(categoria: str, check: str, index: int) -> str:
    prefix = categoria[:3].upper()
    return f"TKT-{prefix}-{index:03d}"


def generate_tickets(audit: AuditInput) -> List[Ticket]:
    tickets: List[Ticket] = []
    counter: Dict[str, int] = {}

    def next_id(cat: str) -> str:
        counter[cat] = counter.get(cat, 0) + 1
        return _ticket_id(cat, "", counter[cat])

    # 1. Critical errors first
    for error_key in audit.errores:
        cfg = ERROR_CONFIG.get(error_key)
        if not cfg:
            continue
        titulo, categoria, impacto, estimacion = cfg
        tickets.append(
            Ticket(
                id=next_id(categoria),
                categoria=categoria,
                titulo=titulo,
                prioridad=Prioridad.Critica,
                impacto=impacto,
                agente=AGENT_MAP[categoria],
                estimacion=estimacion,
                dependencias=[],
                estado=EstadoTicket.OPEN,
            )
        )

    # 2. Failed checks
    for cat_str, checks in audit.checks.items():
        cat_cfg = CHECK_CONFIG.get(cat_str)
        if not cat_cfg:
            continue
        for check_name, passed in checks.items():
            if passed:
                continue
            cfg = cat_cfg.get(check_name)
            if not cfg:
                continue
            titulo, prioridad, impacto, estimacion = cfg
            tickets.append(
                Ticket(
                    id=next_id(cat_str),
                    categoria=cat_str,
                    titulo=titulo,
                    prioridad=prioridad,
                    impacto=impacto,
                    agente=AGENT_MAP[cat_str],
                    estimacion=estimacion,
                    dependencias=[],
                    estado=EstadoTicket.OPEN,
                )
            )

    # 3. Inject cross-category dependencies
    critica_ids = [t.id for t in tickets if t.prioridad == Prioridad.Critica]
    seguridad_ids = [t.id for t in tickets if t.categoria == Categoria.Seguridad]

    for ticket in tickets:
        # Every non-critical ticket depends on critical ones being resolved first
        if ticket.prioridad != Prioridad.Critica and critica_ids:
            ticket.dependencias = list(set(ticket.dependencias + critica_ids))

        # Performance and WooCommerce depend on Seguridad fixes
        if ticket.categoria in (Categoria.Performance, Categoria.WooCommerce):
            ticket.dependencias = list(set(ticket.dependencias + seguridad_ids))

    # 4. Sort: Critica → Alta → Media → Baja, then by estimacion asc within same priority
    tickets.sort(key=lambda t: (PRIORITY_ORDER[t.prioridad], t.estimacion))

    return tickets
