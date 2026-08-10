"""
Capa de datos de CLIENTES (captura en el flujo de venta del TPV, multiempresa).

Cliente reutilizable (nombre, NIF, contacto) que se asocia a la venta. La venta
guarda además el nombre/NIF denormalizados para que el ticket y la búsqueda sean
robustos aunque el cliente cambie. Filtra por ``id_empresa``.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("clientes_db")


def _fila(cur, row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(zip([d[0] for d in cur.description], row))


def buscar_clientes(texto="", id_empresa=None, limite=50) -> list[dict]:
    """Busca clientes por nombre, NIF, teléfono o email."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            params = [id_empresa]
            sql = ("SELECT * FROM clientes WHERE id_empresa=%s AND estado='activo'")
            if texto:
                sql += " AND (nombre LIKE %s OR nif LIKE %s OR telefono LIKE %s OR email LIKE %s)"
                params += [f"%{texto}%"] * 4
            sql += " ORDER BY nombre ASC LIMIT %s"
            params.append(int(limite))
            cur.execute(sql, params)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Error buscar_clientes: %s", e)
        return []


def obtener_cliente(cliente_id) -> dict | None:
    if not cliente_id:
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM clientes WHERE id=%s", (cliente_id,))
            return _fila(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_cliente(%s): %s", cliente_id, e)
        return None


def buscar_cliente_por_codigo(codigo, id_empresa=None) -> dict | None:
    """Resuelve un cliente a partir del código escaneado de su tarjeta (QR/código de barras).
    Acepta: id numérico del cliente, o NIF/teléfono/email exacto. Devuelve el cliente o None."""
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    # 1) id numérico del cliente.
    if codigo.isdigit():
        c = obtener_cliente(int(codigo))
        if c:
            return c
    # 2) coincidencia EXACTA por NIF / teléfono / email.
    cl = codigo.lower()
    for c in buscar_clientes(codigo, id_empresa=id_empresa, limite=10):
        for campo in ("nif", "telefono", "email"):
            if str(c.get(campo) or "").strip().lower() == cl:
                return c
    # 3) una única coincidencia por texto.
    res = buscar_clientes(codigo, id_empresa=id_empresa, limite=2)
    return res[0] if len(res) == 1 else None


def crear_cliente(nombre, nif=None, telefono=None, email=None,
                  direccion=None, id_empresa=None, *, cp=None, poblacion=None,
                  provincia=None, pais=None) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    if not (nombre or "").strip():
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Inserta solo las columnas de domicilio que existan (migr 0068).
            cols = {"nombre": nombre.strip(), "nif": nif or None, "telefono": telefono or None,
                    "email": email or None, "direccion": direccion or None,
                    "id_empresa": id_empresa}
            try:
                existentes = {r["Field"] if isinstance(r, dict) else r[0]
                              for r in (cur.execute("SHOW COLUMNS FROM clientes"), cur.fetchall())[1]}
            except Exception:
                existentes = set(cols)
            for k, v in (("cp", cp), ("poblacion", poblacion), ("provincia", provincia), ("pais", pais)):
                if k in existentes and v:
                    cols[k] = v
            campos = ", ".join(cols)
            marcas = ", ".join(["%s"] * len(cols))
            cur.execute(f"INSERT INTO clientes ({campos}) VALUES ({marcas})", tuple(cols.values()))
            conn.commit()
            _cid = cur.lastrowid
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("CLIENTE_CREADO", id_empresa=id_empresa, origen="crm",
                         ref_entidad="cliente", ref_id=_cid,
                         payload={"nombre": (nombre or "").strip(), "nif": nif or None})
        except Exception:
            pass
        return _cid
    except Exception as e:
        logger.error("Error crear_cliente: %s", e)
        return None


# ── VTA.1 — CRUD completo + segmentación/crédito ──────────────────────────────
_PERMITIDOS = ("nombre", "nif", "telefono", "email", "direccion", "estado",
               "limite_credito", "riesgo_actual", "categoria", "segmento",
               "observaciones", "estado_crediticio",
               # Domicilio fiscal (migr 0068) — facturación
               "cp", "poblacion", "provincia", "pais",
               # AEAT-6 — dimensión intracomunitaria (Modelo 349)
               "nif_iva", "es_intracomunitario", "pais_fiscal",
               # FASE 3.1 — atributos fiscales del cliente (migr 0076)
               "regimen_fiscal", "tipo_operacion", "aplica_recargo_equivalencia",
               "aplica_retencion_irpf", "porcentaje_retencion", "validacion_vies",
               "es_extranjero", "aplica_isp", "condiciones_pago")


# Regímenes fiscales soportados (origen: cliente.regimen_fiscal).
REGIMENES_FISCALES = ("general", "recargo", "exento", "intracomunitario", "extranjero", "isp")


def perfil_fiscal(cliente) -> dict:
    """ORIGEN ÚNICO de decisión fiscal de la factura a partir del cliente.

    Acepta un dict de cliente o un id (lo resuelve). Devuelve un perfil normalizado y
    seguro (defaults neutros) que consumirá el motor fiscal (FASE 3.2) para determinar
    automáticamente IVA / recargo / ISP / exención intracomunitaria / IRPF sin intervención
    manual. Si el cliente no tiene datos fiscales (o no hay cliente), el perfil es el
    GENERAL → comportamiento idéntico al actual."""
    if isinstance(cliente, (int, str)):
        cliente = obtener_cliente(cliente) or {}
    c = cliente or {}

    def _b(k):
        v = c.get(k)
        return bool(int(v)) if str(v).strip() not in ("", "None") else False

    regimen = (c.get("regimen_fiscal") or "general").strip().lower()
    if regimen not in REGIMENES_FISCALES:
        regimen = "general"
    # Banderas derivadas (régimen explícito O flags individuales, lo que sea verdadero).
    recargo = _b("aplica_recargo_equivalencia") or regimen == "recargo"
    isp = _b("aplica_isp") or regimen == "isp"
    intracom = _b("es_intracomunitario") or regimen == "intracomunitario"
    extranjero = _b("es_extranjero") or regimen == "extranjero"
    exento = regimen == "exento"
    irpf = _b("aplica_retencion_irpf")
    try:
        pct_irpf = float(c.get("porcentaje_retencion") or 0)
    except Exception:
        pct_irpf = 0.0
    return {
        "regimen": regimen,
        "recargo_equivalencia": recargo,
        "isp": isp,
        "intracomunitario": intracom,
        "extranjero": extranjero,
        "exento": exento,
        "retencion_irpf": irpf and pct_irpf > 0,
        "porcentaje_retencion": pct_irpf,
        "nif_iva": c.get("nif_iva") or None,
        "vies": (c.get("validacion_vies") or None),
        "pais_fiscal": (c.get("pais_fiscal") or None),
        "condiciones_pago": c.get("condiciones_pago") or None,
    }


def actualizar_cliente(cliente_id, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE clientes SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), cliente_id, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_cliente(%s): %s", cliente_id, e)
        return False


def eliminar_cliente(cliente_id, id_empresa=None) -> bool:
    """Baja LÓGICA (estado=inactivo) para no romper histórico de ventas."""
    return actualizar_cliente(cliente_id, id_empresa=id_empresa, estado="inactivo")


def activar_cliente(cliente_id, activo=True, id_empresa=None) -> bool:
    return actualizar_cliente(cliente_id, id_empresa=id_empresa,
                              estado="activo" if activo else "inactivo")


def listar_clientes(id_empresa=None, segmento=None, estado=None, limite=500) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    cond, params = ["id_empresa=%s"], [id_empresa]
    if segmento:
        cond.append("segmento=%s"); params.append(segmento)
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM clientes WHERE {' AND '.join(cond)} "
                        "ORDER BY nombre LIMIT %s", (*params, int(limite)))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_clientes: %s", e)
        return []


# ── Contactos / Direcciones ───────────────────────────────────────────────────
def agregar_contacto(cliente_id, nombre, cargo=None, email=None, telefono=None,
                     id_empresa=None) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO clientes_contactos (id_cliente, id_empresa, nombre, cargo, "
                        "email, telefono) VALUES (%s,%s,%s,%s,%s,%s)",
                        (cliente_id, id_empresa, nombre, cargo, email, telefono))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("agregar_contacto: %s", e)
        return None


def listar_contactos(cliente_id, id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM clientes_contactos WHERE id_cliente=%s AND id_empresa=%s "
                        "ORDER BY id", (cliente_id, id_empresa))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_contactos: %s", e)
        return []


def agregar_direccion(cliente_id, direccion=None, tipo="envio", cp=None, municipio=None,
                      provincia=None, pais=None, id_empresa=None) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO clientes_direcciones (id_cliente, id_empresa, tipo, direccion, "
                        "cp, municipio, provincia, pais) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (cliente_id, id_empresa, tipo, direccion, cp, municipio, provincia, pais))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("agregar_direccion: %s", e)
        return None


def listar_direcciones(cliente_id, id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM clientes_direcciones WHERE id_cliente=%s AND id_empresa=%s "
                        "ORDER BY id", (cliente_id, id_empresa))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_direcciones: %s", e)
        return []


# ── Historial comercial ───────────────────────────────────────────────────────
def historial_comercial(cliente_id, id_empresa=None) -> dict:
    """Ventas + devoluciones + saldo del cliente (resumen 360º)."""
    id_empresa = id_empresa or empresa_actual_id()
    out = {"ventas": [], "devoluciones": [], "total_ventas": 0.0, "total_devoluciones": 0.0,
           "saldo": 0.0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, fecha, total, forma_pago FROM ventas WHERE cliente_id=%s "
                        "AND id_empresa=%s ORDER BY fecha DESC LIMIT 500", (cliente_id, id_empresa))
            out["ventas"] = [_fila(cur, r) for r in cur.fetchall()]
            out["total_ventas"] = round(sum(float(v["total"] or 0) for v in out["ventas"]), 2)
            cur.execute("SELECT d.id, d.fecha, d.total_reembolso FROM devoluciones d "
                        "JOIN ventas v ON v.id=d.venta_original_id WHERE v.cliente_id=%s "
                        "AND d.id_empresa=%s ORDER BY d.fecha DESC LIMIT 500", (cliente_id, id_empresa))
            out["devoluciones"] = [_fila(cur, r) for r in cur.fetchall()]
            out["total_devoluciones"] = round(
                sum(float(d["total_reembolso"] or 0) for d in out["devoluciones"]), 2)
        out["saldo"] = round(out["total_ventas"] - out["total_devoluciones"], 2)
        return out
    except Exception as e:
        logger.error("historial_comercial(%s): %s", cliente_id, e)
        return out
