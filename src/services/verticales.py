"""
Ediciones / verticales por tipo de comercio (SEGMENTACIÓN DE PRODUCTO). Misma base y mismas tarifas para todas;
según el negocio, algunas funciones se OCULTAN o se SUSTITUYEN por otras. Motor ÚNICO con una matriz de reglas
(fuente de verdad). Ortogonal a entitlements (plan): la edición = tipo de negocio; el plan = lo contratado.

La edición se resuelve así: (1) variable de entorno `SMART_MANAGER_EDITION` (override / aprovisionamiento SaaS)
→ (2) elección de ONBOARDING persistida por instalación (JSON local `config_edicion.json`, escrita la primera
vez que el negocio elige su tipo de comercio) → (3) por defecto SUPERMARKET (la más completa). Cada instalación
ES una edición (producto separado); NO es por empresa.

La GUI consulta `visible("tpv.bascula")` / `sustituto(...)` para mostrar/ocultar/reemplazar; NUNCA se elimina
código: se gatea (así una misma base sirve a todas las ediciones). El nombre de la app: `nombre_edicion()` →
"Smart Manager Supermarket".
"""

import logging
import os

logger = logging.getLogger("verticales")

VERTICALES = ("SUPERMARKET", "RETAIL", "PHARMACY", "TEXTIL", "BAKERY")
DEFECTO = "SUPERMARKET"

_NOMBRES = {"SUPERMARKET": "Supermarket", "RETAIL": "Retail", "PHARMACY": "Pharmacy",
            "TEXTIL": "Textil", "BAKERY": "Bakery & Coffee"}

# Catálogo de funciones segmentables (clave → etiqueta legible para la pantalla de administración).
FUNCIONES = {
    "tpv.bascula": "TPV · Báscula (venta a granel)",
    "productos.granel": "Productos · A granel",
    "productos.tallas": "Productos · Tallas y colores (variantes)",
    "productos.lotes": "Productos · Lotes y caducidad",
    "pharmacy.recetas": "Farmacia · Recetas / dispensación",
    "bakery.obrador": "Panadería · Obrador / producción diaria",
    "almacenes.mrp": "Almacenes · MRP / Fabricación (industrial)",
    "tpv.autocobro": "TPV · Autocobro / self-checkout (verificación de edad)",
    "tpv.venta_almacen": "TPV · Venta desde almacén (pedidos online al almacén central)",
    "tpv.tarjeta_regalo": "TPV · Tarjeta regalo",
    "tpv.devolucion": "TPV · Devoluciones",
    "catalogo.web": "Comercio · Catálogo Web (tienda online)",
    # Funciones BASE (R8) — capacidades transversales, NO ediciones; visibles en las versiones que corresponden.
    "transporte.reparto": "Reparto · Flota y rutas de reparto",
    "distribucion.expedicion": "Distribución · Pedidos, picking y expediciones (B2B)",
    "compras.subastas": "Compras · Subastas del mercado (pujas)",
    "compras.bolsa": "Compras · Bolsa de proveedores y mercado (Lonja) + Portal proveedor",
}

# MATRIZ (fuente de verdad). Solo se listan las DIFERENCIAS respecto a la base (todo VISIBLE por defecto).
# funcion → {vertical: "oculto" | "por:<funcion_sustituta>"}.
_REGLAS = {
    # Báscula/granel: en Bakery se vende por UNIDAD (nunca a granel) → oculto. En Textil, la báscula se
    # sustituye por variantes talla/color.
    "tpv.bascula":      {"RETAIL": "oculto", "PHARMACY": "oculto", "TEXTIL": "por:productos.tallas",
                         "BAKERY": "oculto"},
    "productos.granel": {"RETAIL": "oculto", "PHARMACY": "oculto", "TEXTIL": "oculto", "BAKERY": "oculto"},
    # Variantes talla/color: visible en SUPERMARKET (venden ropa/textil), RETAIL y TEXTIL; oculto en farmacia/panadería.
    "productos.tallas": {"PHARMACY": "oculto", "BAKERY": "oculto"},
    "productos.lotes":  {"TEXTIL": "oculto"},
    "pharmacy.recetas": {"SUPERMARKET": "oculto", "RETAIL": "oculto", "TEXTIL": "oculto", "BAKERY": "oculto"},
    "bakery.obrador":   {"SUPERMARKET": "oculto", "RETAIL": "oculto", "PHARMACY": "oculto", "TEXTIL": "oculto"},
    # Autocobro / self-checkout (con verificación de edad) = SOLO Supermarket. En el resto de ediciones no existe.
    "tpv.autocobro":    {"RETAIL": "oculto", "PHARMACY": "oculto", "TEXTIL": "oculto", "BAKERY": "oculto"},
    # En Bakery el TPV se simplifica (venta rápida por unidad): NO hay venta desde almacén (pedidos online),
    # ni tarjeta regalo, ni devoluciones.
    "tpv.venta_almacen":  {"BAKERY": "oculto"},
    "tpv.tarjeta_regalo": {"BAKERY": "oculto"},
    "tpv.devolucion":     {"BAKERY": "oculto"},
    # Catálogo Web (tienda online): en Bakery se usa carta física en el local → oculto.
    "catalogo.web":     {"BAKERY": "oculto"},
    # MRP/Fabricación industrial: oculto en Pharmacy; en Bakery se SUSTITUYE por el Obrador.
    "almacenes.mrp":    {"PHARMACY": "oculto", "BAKERY": "por:bakery.obrador"},
    # ── Funciones BASE (R8): capacidades transversales, NO ediciones. Su visibilidad por VERSIÓN se
    #    decide aquí (se incluyen en las versiones que corresponden; ampliar/reducir = editar la línea). ──
    # Flota y rutas de reparto: comercio general con reparto → Supermarket, Retail, Pharmacy y Textil.
    "transporte.reparto": {"BAKERY": "oculto"},
    # Distribución mayorista B2B (venta a clientes → picking → expedición): solo en comercio general con
    # almacén → Supermarket, Retail y Textil. Oculta en Pharmacy y Bakery.
    "distribucion.expedicion": {"PHARMACY": "oculto", "BAKERY": "oculto"},
    # Subastas del mercado (pujas): SOLO comercio general de gran volumen → Supermarket y Retail. En
    # Pharmacy/Textil/Bakery se ocultan (el resto del módulo de proveedores sigue disponible en todas).
    "compras.subastas": {"PHARMACY": "oculto", "TEXTIL": "oculto", "BAKERY": "oculto"},
    # Bolsa de proveedores + mercado (Lonja) + Portal proveedor web: SOLO comercio general de gran volumen
    # (Supermarket/Retail). En Pharmacy/Textil/Bakery el flujo de compras es SIMPLE (pedido bajo encargo al
    # proveedor registrado): se oculta la bolsa/mercado, la cola de subastas y la pestaña Portal proveedor.
    "compras.bolsa": {"PHARMACY": "oculto", "TEXTIL": "oculto", "BAKERY": "oculto"},
}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _normaliza(v) -> str | None:
    v = (v or "").strip().upper()
    if v in ("BAKERY & COFFEE", "BAKERY_COFFEE", "COFFEE"):
        v = "BAKERY"
    return v if v in VERTICALES else None


# ── Persistencia de la elección de ONBOARDING (per-install, sin BD; patrón `utils/tema`) ──
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_CONFIG = os.path.join(_RAIZ, "config_edicion.json")


def edicion_configurada() -> str | None:
    """Edición elegida en el onboarding y persistida en `config_edicion.json` (o None si aún no se eligió).
    Tolerante a fallos: fichero inexistente/corrupto → None."""
    try:
        import json
        with open(RUTA_CONFIG, "r", encoding="utf-8") as fh:
            return _normaliza((json.load(fh) or {}).get("edicion"))
    except Exception:
        return None


def fijar_edicion(vertical) -> bool:
    """Persiste la edición elegida en el onboarding (per-install). Valida contra VERTICALES. Devuelve True si OK."""
    v = _normaliza(vertical)
    if not v:
        return False
    try:
        import json
        with open(RUTA_CONFIG, "w", encoding="utf-8") as fh:
            json.dump({"edicion": v}, fh, ensure_ascii=False, indent=2)
        logger.info("Edición fijada por onboarding: %s", v)
        return True
    except Exception as e:
        logger.error("fijar_edicion(%s): %s", vertical, e)
        return False


def edicion_definida() -> bool:
    """¿La instalación ya tiene edición decidida? True si viene por entorno (override/SaaS) o por onboarding
    persistido. False → hay que preguntar al negocio su tipo de comercio (primera ejecución)."""
    return bool(_normaliza(os.getenv("SMART_MANAGER_EDITION") or os.getenv("SM_EDITION"))
                or edicion_configurada())


def vertical_actual(id_empresa=None) -> str:
    """Edición efectiva de la INSTALACIÓN. Prioridad: entorno `SMART_MANAGER_EDITION` (override / SaaS) →
    onboarding persistido (`config_edicion.json`) → SUPERMARKET por defecto. Cada instalación ES una edición
    (producto separado); NO es por empresa. `id_empresa` se acepta por compatibilidad de firma pero se ignora."""
    return (_normaliza(os.getenv("SMART_MANAGER_EDITION") or os.getenv("SM_EDITION"))
            or edicion_configurada() or DEFECTO)


def edicion() -> str:
    """Código de la edición actual (SUPERMARKET/RETAIL/PHARMACY/TEXTIL/BAKERY)."""
    return vertical_actual()


def nombre_edicion(id_empresa=None, *, vertical=None) -> str:
    """'Smart Manager Supermarket' (el nombre de la edición se añade tras 'Smart Manager')."""
    v = _normaliza(vertical) or vertical_actual(id_empresa)
    return f"Smart Manager {_NOMBRES.get(v, '')}".strip()


def estado(funcion, id_empresa=None, *, vertical=None) -> str:
    """'visible' | 'oculto' | 'sustituida' para la función en la edición efectiva."""
    v = _normaliza(vertical) or vertical_actual(id_empresa)
    regla = _REGLAS.get(funcion, {}).get(v)
    if regla is None:
        return "visible"
    if regla == "oculto":
        return "oculto"
    if regla.startswith("por:"):
        return "sustituida"
    return "visible"


def visible(funcion, id_empresa=None, *, vertical=None) -> bool:
    """¿Se muestra la función en esta edición? (False si está oculta o sustituida por otra)."""
    return estado(funcion, id_empresa, vertical=vertical) == "visible"


def sustituto(funcion, id_empresa=None, *, vertical=None) -> str | None:
    """Función que SUSTITUYE a `funcion` en esta edición (o None)."""
    v = _normaliza(vertical) or vertical_actual(id_empresa)
    regla = _REGLAS.get(funcion, {}).get(v)
    return regla[4:] if (regla and regla.startswith("por:")) else None


def funciones(id_empresa=None, *, vertical=None) -> list:
    """Estado de todas las funciones segmentables en la edición (para la pantalla de administración)."""
    v = _normaliza(vertical) or vertical_actual(id_empresa)
    return [{"funcion": f, "label": lbl, "estado": estado(f, vertical=v), "sustituto": sustituto(f, vertical=v)}
            for f, lbl in FUNCIONES.items()]


# ── Datos por defecto de cada edición (versión "llave en mano") ───────────────
# Familias de producto típicas de cada comercio; se siembran al provisionar la empresa.
_FAMILIAS_DEFECTO = {
    "SUPERMARKET": ["Alimentación", "Bebidas", "Frescos", "Congelados", "Limpieza", "Droguería"],
    "RETAIL": ["General", "Electrónica", "Hogar", "Papelería", "Regalos"],
    "PHARMACY": ["Medicamentos", "Parafarmacia", "Higiene", "Dermocosmética", "Ortopedia"],
    "TEXTIL": ["Ropa", "Calzado", "Complementos", "Ropa interior", "Deporte"],
    "BAKERY": ["Dulce", "Salado", "Bebidas"],
}


# Catálogo de productos por defecto de la edición (versión "llave en mano"). Por ahora solo BAKERY, cuyo
# TPV es una rejilla de venta rápida por unidad. {familia: [(codigo, nombre, precio), ...]}.
_PRODUCTOS_DEFECTO = {
    "BAKERY": {
        # (codigo, nombre, precio, emoji)
        "Salado": [
            ("BK-SAL01", "Bocadillo vegetal", 3.50, "🥪"), ("BK-SAL02", "Bocadillo de atún", 3.50, "🥪"),
            ("BK-SAL03", "Bocadillo de jamón serrano", 4.00, "🥪"),
            ("BK-SAL04", "Bocadillo de queso", 3.20, "🥪"),
            ("BK-SAL05", "Bocadillo de tortilla", 3.30, "🥪"),
            ("BK-SAL06", "Bocadillo de tortilla de patata", 3.80, "🥪"),
            ("BK-SAL07", "Porción pizza barbacoa", 2.80, "🍕"), ("BK-SAL08", "Porción pizza atún", 2.80, "🍕"),
            ("BK-SAL09", "Panini de atún", 4.20, "🥙"), ("BK-SAL10", "Panini barbacoa", 4.50, "🥙"),
            # extras sugeridos
            ("BK-SAL11", "Bocadillo de lomo", 4.00, "🥪"), ("BK-SAL12", "Empanada", 2.50, "🥟"),
            ("BK-SAL13", "Croqueta", 1.20, "🧆"),
        ],
        "Dulce": [
            ("BK-DUL01", "Croissant", 1.20, "🥐"), ("BK-DUL02", "Donut", 1.30, "🍩"),
            ("BK-DUL03", "Croissant de chocolate", 1.60, "🥐"), ("BK-DUL04", "Berlina", 1.50, "🍩"),
            ("BK-DUL05", "Magdalena", 0.90, "🧁"), ("BK-DUL06", "Magdalena de chocolate", 1.00, "🧁"),
            ("BK-DUL07", "Porción de pastel", 3.00, "🍰"), ("BK-DUL08", "Galleta", 0.80, "🍪"),
            ("BK-DUL09", "Galleta de chocolate", 0.90, "🍪"),
            # extras sugeridos
            ("BK-DUL10", "Napolitana de chocolate", 1.50, "🥐"), ("BK-DUL11", "Ensaimada", 1.80, "🥐"),
            ("BK-DUL12", "Palmera", 1.40, "🥐"),
        ],
        "Bebidas": [
            ("BK-BEB01", "Café solo", 1.10, "☕"), ("BK-BEB02", "Café con leche", 1.30, "☕"),
            ("BK-BEB03", "Capuchino", 1.60, "☕"), ("BK-BEB04", "Expreso", 1.10, "☕"),
            ("BK-BEB05", "Macchiato", 1.50, "☕"), ("BK-BEB06", "Zumo de naranja", 2.20, "🧃"),
            ("BK-BEB07", "Botella de agua", 1.00, "💧"),
            # extras sugeridos
            ("BK-BEB08", "Cortado", 1.20, "☕"), ("BK-BEB09", "Café bombón", 1.60, "☕"),
            ("BK-BEB10", "Té", 1.30, "🍵"), ("BK-BEB11", "Chocolate caliente", 2.00, "☕"),
            ("BK-BEB12", "Refresco", 1.80, "🥤"),
        ],
    },
}


def familias_por_defecto(*, vertical=None) -> list:
    """Familias de producto por defecto de la edición."""
    return list(_FAMILIAS_DEFECTO.get(_normaliza(vertical) or vertical_actual(), []))


def productos_por_defecto(*, vertical=None) -> dict:
    """Catálogo de productos por defecto de la edición ({familia: [(codigo, nombre, precio), ...]})."""
    return dict(_PRODUCTOS_DEFECTO.get(_normaliza(vertical) or vertical_actual(), {}))


def _sembrar_productos(emp, v) -> int:
    """Siembra el catálogo por defecto de la edición (get-or-create por código, NO destructivo: no pisa
    precios/nombres editados por el comercio). Asigna cada producto a su familia. Devuelve nº creados."""
    catalogo = _PRODUCTOS_DEFECTO.get(v)
    if not catalogo:
        return 0
    creados = 0
    try:
        from src.db import familias as F
        from src.db.conexion import obtener_conexion
        idx = {str(f.get("nombre") or "").strip().lower(): (f.get("id") or f.get("id_familia"))
               for f in F.listar_familias(emp, solo_activas=False)}
        with obtener_conexion() as conn, conn.cursor() as cur:
            for fam, prods in catalogo.items():
                fid = idx.get(fam.lower())
                if fid is None:
                    continue
                for cod, nombre, precio, emoji in prods:
                    # NO destructivo: no pisa nombre/precio editados por el comercio; SÍ rellena el emoji si
                    # aún está vacío (backfill para productos ya sembrados antes de existir la columna).
                    cur.execute(
                        "INSERT INTO articulos (codigo, id_empresa, nombre, precio, seccion, id_familia, "
                        "emoji, Stock_tienda, Stock_total, estado) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'activo') "
                        "ON DUPLICATE KEY UPDATE emoji=COALESCE(NULLIF(emoji,''), VALUES(emoji))",
                        (cod, emp, nombre, float(precio), fam, fid, emoji, 100, 100))
                    if cur.rowcount == 1:      # 1 = insertado nuevo (2 = actualizado emoji; 0 = sin cambios)
                        creados += 1
            conn.commit()
    except Exception as e:
        logger.error("_sembrar_productos: %s", e)
    return creados


def aplicar_datos_por_defecto(id_empresa=None, *, vertical=None) -> dict:
    """Siembra los datos por defecto de la edición (familias típicas del comercio) al provisionar una empresa.
    IDEMPOTENTE (get-or-create por nombre). Reutiliza `db/familias` (N7). Devuelve {vertical, familias_creadas}."""
    emp = _emp(id_empresa)
    v = _normaliza(vertical) or vertical_actual()
    if not emp:
        return {"ok": False, "vertical": v, "familias_creadas": 0}
    creadas = 0
    try:
        from src.db import familias as F
        existentes = {str(f.get("nombre") or "").strip().lower()
                      for f in F.listar_familias(emp, solo_activas=False)}
        for nombre in familias_por_defecto(vertical=v):
            if nombre.strip().lower() not in existentes and F.crear_familia(nombre, id_empresa=emp):
                creadas += 1
                existentes.add(nombre.strip().lower())
    except Exception as e:
        logger.error("aplicar_datos_por_defecto: %s", e)
        return {"ok": False, "vertical": v, "familias_creadas": creadas}
    # Tras las familias, sembrar el catálogo de productos por defecto de la edición (idempotente).
    productos_creados = _sembrar_productos(emp, v)
    return {"ok": True, "vertical": v, "familias_creadas": creadas, "productos_creados": productos_creados}
