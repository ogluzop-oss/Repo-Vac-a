"""
Vales descuento de devoluciones — tercer método de reembolso del TPV (junto a efectivo/tarjeta),
para empresas cuya política es NO devolver dinero, solo un vale canjeable en la próxima compra.

No caducan. Son válidos en CUALQUIER tienda de la empresa (se escopan solo por `id_empresa`, nunca
por tienda, mismo criterio que el motor de cupones promocionales — ver migración 0314). El cliente
puede canjear el vale aunque su importe sea mayor que la compra: se aplica como pago hasta agotar
la compra y, si sobra importe, el vale ACTUAL se desactiva para siempre y se emite uno NUEVO con el
saldo restante (nunca se reactiva/edita el mismo registro — cada vale es de un solo uso, total o
parcial).
"""

from __future__ import annotations

import logging
import secrets

logger = logging.getLogger("tpv.vales_devolucion")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _emp(id_empresa=None):
    from src.db.conexion import EMPRESA_DEFAULT_ID
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id() or EMPRESA_DEFAULT_ID
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila_a_dict(cur, fila):
    if fila is None:
        return None
    if isinstance(fila, dict):
        return fila
    columnas = [d[0] for d in cur.description]
    return dict(zip(columnas, fila, strict=False))


def _generar_codigo() -> str:
    """`VALE-XXXXXXXXXXXX` (12 hex, mayúsculas) — suficientemente corto para un Code128 legible en
    un ticket de 80mm, suficientemente largo para no colisionar en la práctica."""
    return f"VALE-{secrets.token_hex(6).upper()}"


def emitir_vale(importe, *, id_empresa=None, id_devolucion=None, id_vale_origen=None,
                id_tienda_emision=None) -> dict | None:
    """Crea un vale ACTIVO por `importe`. Devuelve {id, codigo, importe} o None si falla. Nunca
    reutiliza un código existente (reintenta en el improbable caso de colisión)."""
    importe = round(float(importe or 0), 2)
    if importe <= 0:
        logger.warning("emitir_vale: importe inválido (%s)", importe)
        return None
    id_empresa = _emp(id_empresa)
    for _intento in range(5):
        codigo = _generar_codigo()
        try:
            with _conn() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO vales_devolucion (id_empresa, codigo, importe, importe_original, "
                    "estado, id_devolucion, id_vale_origen, id_tienda_emision) "
                    "VALUES (%s,%s,%s,%s,'activo',%s,%s,%s)",
                    (id_empresa, codigo, importe, importe, id_devolucion, id_vale_origen,
                     id_tienda_emision))
                nuevo_id = cur.lastrowid
                conn.commit()
            return {"id": nuevo_id, "codigo": codigo, "importe": importe}
        except Exception as e:
            if "Duplicate" in str(e) or "uq_vale_devolucion" in str(e):
                continue
            logger.error("emitir_vale: %s", e)
            return None
    logger.error("emitir_vale: no se pudo generar un código único tras varios intentos")
    return None


def buscar_vale(codigo, *, id_empresa=None) -> dict | None:
    """Busca el vale por código, SIEMPRE a nivel de empresa (nunca de tienda) — es lo que permite
    canjearlo en cualquier tienda."""
    id_empresa = _emp(id_empresa)
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM vales_devolucion WHERE codigo=%s AND id_empresa=%s",
                       (codigo, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("buscar_vale: %s", e)
        return None


def validar_vale(codigo, *, id_empresa=None) -> tuple[bool, str, dict | None]:
    """(ok, motivo, vale). `ok=False` con motivo explícito si no existe o ya se canjeó — nunca deja
    canjear dos veces un mismo código."""
    vale = buscar_vale(codigo, id_empresa=id_empresa)
    if not vale:
        return False, "Vale no encontrado.", None
    if vale.get("estado") != "activo":
        return False, "Este vale ya ha sido canjeado.", vale
    return True, "", vale


def canjear_vale(codigo, importe_compra, *, id_empresa=None, id_venta=None,
                 id_tienda_canje=None) -> dict:
    """Canjea el vale contra una compra de `importe_compra`. El vale se aplica SIEMPRE entero (el
    cliente puede usarlo aunque la compra sea menor que su importe): se descuenta de la compra
    hasta `min(importe_compra, vale.importe)` y, si sobra saldo, el vale actual se desactiva y se
    emite uno NUEVO con el sobrante (nunca se reutiliza el mismo código).

    Devuelve {ok, motivo, aplicado, sobrante, vale_nuevo:{id,codigo,importe}|None}."""
    id_empresa = _emp(id_empresa)
    ok, motivo, vale = validar_vale(codigo, id_empresa=id_empresa)
    if not ok:
        return {"ok": False, "motivo": motivo, "aplicado": 0, "sobrante": 0, "vale_nuevo": None}

    importe_compra = round(float(importe_compra or 0), 2)
    importe_vale = float(vale["importe"])
    aplicado = round(min(importe_compra, importe_vale), 2) if importe_compra > 0 else importe_vale
    sobrante = round(importe_vale - aplicado, 2)

    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE vales_devolucion SET estado='canjeado', fecha_canje=NOW(), "
                "id_venta_canje=%s, id_tienda_canje=%s WHERE id=%s AND id_empresa=%s AND estado='activo'",
                (id_venta, id_tienda_canje, vale["id"], id_empresa))
            if cur.rowcount != 1:
                # Canjeado por otra caja entre la validación y este UPDATE (condición de carrera) —
                # nunca se continúa: evita aplicar dos veces el mismo vale.
                conn.rollback()
                return {"ok": False, "motivo": "Este vale ya ha sido canjeado.",
                       "aplicado": 0, "sobrante": 0, "vale_nuevo": None}
            conn.commit()
    except Exception as e:
        logger.error("canjear_vale: %s", e)
        return {"ok": False, "motivo": "Error al canjear el vale.", "aplicado": 0,
               "sobrante": 0, "vale_nuevo": None}

    vale_nuevo = None
    if sobrante > 0:
        vale_nuevo = emitir_vale(sobrante, id_empresa=id_empresa, id_vale_origen=vale["id"],
                                 id_tienda_emision=id_tienda_canje)
        if not vale_nuevo:
            logger.error("canjear_vale: el vale %s se canjeó pero no se pudo emitir el vale del "
                        "sobrante (%.2f) — requiere alta manual.", codigo, sobrante)

    return {"ok": True, "motivo": "", "aplicado": aplicado, "sobrante": sobrante,
           "vale_nuevo": vale_nuevo}
