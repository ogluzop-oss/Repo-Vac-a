"""
Capa de datos de PROVEEDORES (E2.1).

CRUD de proveedores + contactos + direcciones, multiempresa por `id_empresa`
(resuelto por el TenantContext si no se indica). Tablas creadas por la migración
C4 `0008_proveedores`. No toca artículos/stock/catálogo.
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             ensure_schema, obtener_conexion)

logger = logging.getLogger("proveedores_db")

ESTADOS = ("activo", "inactivo")


def _empresa(id_empresa=None):
    # IOC v3 (Bloque V): seam de identidad delegado en la fachada de datos (db -> db).
    try:
        from src.db.identidad_contexto import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return EMPRESA_DEFAULT_ID


# ── Proveedores ──────────────────────────────────────────────────────────────
def crear_proveedor(razon_social, cif_nif=None, nombre_comercial=None, email=None,
                    telefono=None, direccion_fiscal=None, observaciones=None,
                    id_empresa=None) -> int | None:
    if not (razon_social or "").strip():
        return None
    id_empresa = _empresa(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO proveedores (id_empresa, razon_social, nombre_comercial, "
                "cif_nif, email, telefono, direccion_fiscal, observaciones) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, razon_social.strip(), nombre_comercial, cif_nif, email,
                 telefono, direccion_fiscal, observaciones))
            pid = cur.lastrowid
            conn.commit()
        try:
            from src.services import eventos as _EV
            _EV.publicar("PROVEEDOR_CREADO", id_empresa=id_empresa, origen="proveedores",
                         ref_entidad="proveedor", ref_id=pid,
                         payload={"razon_social": razon_social.strip()})
        except Exception:
            pass
        return pid
    except Exception as e:
        logger.error("crear_proveedor: %s", e)
        return None


def actualizar_proveedor(id_proveedor, id_empresa=None, **campos) -> bool:
    permitidos = ("razon_social", "nombre_comercial", "cif_nif", "email", "telefono",
                  "direccion_fiscal", "estado", "observaciones",
                  # CMP.1 — condiciones / bancarios / homologación
                  "plazo_pago", "lead_time_dias", "descuento", "rappel", "divisa",
                  "iban", "irpf", "homologado", "bloqueado", "categoria",
                  # AEAT-6 — dimensión intracomunitaria (Modelo 349)
                  "nif_iva", "es_intracomunitario", "pais_fiscal",
                  # Ficha del proveedor (migr 0210) — contacto/comercial
                  "web", "persona_contacto", "forma_pago", "pedido_minimo")
    sets = {k: campos[k] for k in permitidos if k in campos}
    if "estado" in sets and sets["estado"] not in ESTADOS:
        sets.pop("estado")
    if not sets:
        return False
    id_empresa = _empresa(id_empresa)
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE proveedores SET {cols} WHERE id_proveedor=%s AND id_empresa=%s",
                        (*sets.values(), id_proveedor, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        if ok:
            # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
            try:
                from src.services import eventos as _EV
                _EV.publicar("PROVEEDOR_ACTUALIZADO", id_empresa=id_empresa, origen="compras",
                             ref_entidad="proveedor", ref_id=id_proveedor,
                             payload={"campos": list(sets.keys())})
            except Exception:
                pass
        return ok
    except Exception as e:
        logger.error("actualizar_proveedor(%s): %s", id_proveedor, e)
        return False


def obtener_proveedor(id_proveedor, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proveedores WHERE id_proveedor=%s AND id_empresa=%s",
                        (id_proveedor, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_proveedor(%s): %s", id_proveedor, e)
        return None


def listar_proveedores(id_empresa=None, estado=None, texto=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if texto:
        filtros.append("(razon_social LIKE %s OR nombre_comercial LIKE %s OR cif_nif LIKE %s)")
        params += [f"%{texto}%"] * 3
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proveedores WHERE " + " AND ".join(filtros)
                        + " ORDER BY razon_social LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_proveedores: %s", e)
        return []


def eliminar_proveedor(id_proveedor, id_empresa=None) -> bool:
    """Baja LÓGICA (estado=inactivo) para no romper histórico de compras."""
    return actualizar_proveedor(id_proveedor, id_empresa=id_empresa, estado="inactivo")


# ── CMP.1 — Homologación / bloqueo ────────────────────────────────────────────
def esta_bloqueado(id_proveedor, id_empresa=None) -> bool:
    """Un proveedor bloqueado no puede generar pedidos (CMP.2)."""
    p = obtener_proveedor(id_proveedor, id_empresa)
    return bool(p and p.get("bloqueado"))


def esta_homologado(id_proveedor, id_empresa=None) -> bool:
    """Solo proveedores homologados son aptos para aprovisionamiento automático (CMP.7)."""
    p = obtener_proveedor(id_proveedor, id_empresa)
    return bool(p and p.get("homologado"))


def bloquear(id_proveedor, bloqueado=True, id_empresa=None) -> bool:
    return actualizar_proveedor(id_proveedor, id_empresa=id_empresa, bloqueado=1 if bloqueado else 0)


def homologar(id_proveedor, homologado=True, id_empresa=None) -> bool:
    return actualizar_proveedor(id_proveedor, id_empresa=id_empresa, homologado=1 if homologado else 0)


def condiciones_comerciales(id_proveedor, id_empresa=None) -> dict:
    """Condiciones del proveedor (descuento/rappel/plazo/lead time/divisa/irpf)."""
    p = obtener_proveedor(id_proveedor, id_empresa) or {}
    return {k: p.get(k) for k in ("plazo_pago", "lead_time_dias", "descuento", "rappel",
                                  "divisa", "iban", "irpf", "categoria",
                                  "homologado", "bloqueado")}


# ── Contactos ────────────────────────────────────────────────────────────────
def agregar_contacto(id_proveedor, nombre, cargo=None, email=None, telefono=None) -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO proveedores_contactos (id_proveedor, nombre, cargo, email, telefono) "
                "VALUES (%s,%s,%s,%s,%s)", (id_proveedor, nombre, cargo, email, telefono))
            cid = cur.lastrowid
            conn.commit()
            return cid
    except Exception as e:
        logger.error("agregar_contacto(%s): %s", id_proveedor, e)
        return None


def listar_contactos(id_proveedor) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proveedores_contactos WHERE id_proveedor=%s ORDER BY id",
                        (id_proveedor,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_contactos(%s): %s", id_proveedor, e)
        return []


# ── Direcciones ──────────────────────────────────────────────────────────────
def agregar_direccion(id_proveedor, direccion=None, tipo="fiscal", cp=None,
                      municipio=None, provincia=None, pais="España") -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO proveedores_direcciones (id_proveedor, tipo, direccion, cp, "
                "municipio, provincia, pais) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_proveedor, tipo, direccion, cp, municipio, provincia, pais))
            did = cur.lastrowid
            conn.commit()
            return did
    except Exception as e:
        logger.error("agregar_direccion(%s): %s", id_proveedor, e)
        return None


def listar_direcciones(id_proveedor) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proveedores_direcciones WHERE id_proveedor=%s ORDER BY id",
                        (id_proveedor,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_direcciones(%s): %s", id_proveedor, e)
        return []


# ── Perfil fiscal (FASE C — simetría compras↔ventas) ──────────────────────────
# Países UE (código ISO-2 fiscal) — determina intracomunitario vs. extranjero (extra-UE) cuando
# el proveedor no tiene marcado `es_intracomunitario` a mano.
_PAISES_UE = {
    "ES", "FR", "DE", "IT", "PT", "NL", "BE", "AT", "BG", "HR", "CY", "CZ", "DK", "EE", "FI",
    "GR", "EL", "HU", "IE", "LV", "LT", "LU", "MT", "PL", "RO", "SK", "SI", "SE",
}


def perfil_fiscal(proveedor) -> dict:
    """Espejo de `clientes.perfil_fiscal` (MISMA forma de dict) para que
    `utils/fiscalidad.calcular_fiscalidad` — el motor ÚNICO de exención/ISP/intracomunitario, ya
    usado en ventas — se pueda aplicar también a facturas de COMPRA (FASE C, simetría).

    Acepta un dict de proveedor o un id (lo resuelve). A diferencia de `clientes` (que tiene
    columnas de configuración fiscal editables a mano — régimen/recargo/ISP, FASE 3.1),
    `proveedores` solo tiene los campos de la migración 0054 (`nif_iva`/`es_intracomunitario`/
    `pais_fiscal`); el resto del perfil se DERIVA de ahí:
      - proveedor español (o sin país registrado) → régimen GENERAL, todo en falso →
        comportamiento IDÉNTICO al actual (no-op para compras domésticas).
      - proveedor intracomunitario (UE, no España) → ISP/intracomunitario + exento de IVA en
        esta factura (inversión del sujeto pasivo / autorrepercusión del comprador, art. 84.Uno.2º
        LIVA en su variante de adquisición intracomunitaria).
      - proveedor extracomunitario (fuera de la UE) → exento de IVA en esta factura (importación;
        el IVA de importación real se liquida aparte, en aduanas — no es un desarrollo de este
        módulo)."""
    if isinstance(proveedor, (int, str)):
        proveedor = obtener_proveedor(proveedor) or {}
    p = proveedor or {}

    def _b(k):
        v = p.get(k)
        return bool(int(v)) if str(v).strip() not in ("", "None") else False

    pais = (p.get("pais_fiscal") or "ES").upper()
    intracom = _b("es_intracomunitario") or (pais != "ES" and pais in _PAISES_UE)
    extranjero = pais != "ES" and pais not in _PAISES_UE
    isp = intracom
    exento = intracom or extranjero
    regimen = "intracomunitario" if intracom else ("extranjero" if extranjero else "general")
    return {
        "regimen": regimen,
        "recargo_equivalencia": False,
        "isp": isp,
        "intracomunitario": intracom,
        "extranjero": extranjero,
        "exento": exento,
        "retencion_irpf": False,
        "porcentaje_retencion": 0.0,
        "nif_iva": p.get("nif_iva") or None,
        "vies": None,
        "pais_fiscal": (p.get("pais_fiscal") or None),
        "condiciones_pago": None,
    }
