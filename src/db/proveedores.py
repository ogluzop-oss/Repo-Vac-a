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
            return pid
    except Exception as e:
        logger.error("crear_proveedor: %s", e)
        return None


def actualizar_proveedor(id_proveedor, id_empresa=None, **campos) -> bool:
    permitidos = ("razon_social", "nombre_comercial", "cif_nif", "email", "telefono",
                  "direccion_fiscal", "estado", "observaciones",
                  # CMP.1 — condiciones / bancarios / homologación
                  "plazo_pago", "lead_time_dias", "descuento", "rappel", "divisa",
                  "iban", "irpf", "homologado", "bloqueado", "categoria")
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
