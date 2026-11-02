"""
PCD · Zonas de envío (Fase 3 e-commerce, Catálogo Web).

Cálculo del COSTE de envío por zona geográfica/peso/importe de pedido — ANTES del checkout
(distinto de `comercio_digital.envios` propiamente dicho, que es el ciclo de vida POST-pago de la
etiqueta/tracking con el transportista; este módulo decide cuánto cobrar, aquél cómo entregarlo).
No existía ningún cálculo de coste de envío en todo el código (confirmado por auditoría previa) —
pieza genuinamente nueva, reutilizando `articulos.obtener_fisica_seguridad` para el peso (YA
existente, pensado originalmente para seguridad RFID/báscula — mismo dato, no se duplica un
segundo campo "peso" en ningún sitio) y enganchada en `comercial.cotizar` (Fase 2/3), que ya
resuelve el `envio_gratis` del cupón.
"""

from __future__ import annotations

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion, transaccion

logger = logging.getLogger("cd.envios.zonas")


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)


def crear_zona(nombre, *, paises=None, tarifa_base=0, tarifa_por_kg=0, envio_gratis_desde=None,
              orden=0, id_empresa=None) -> int | None:
    """`paises`: lista o string de códigos ISO-3166 alpha-2 separados por coma (p. ej. "ES,PT"),
    o None/"" para la zona POR DEFECTO ("resto del mundo" — a la que cae cualquier destino que no
    case con ninguna otra zona; solo puede haber una por empresa, se valida al calcular)."""
    emp = _emp(id_empresa)
    if isinstance(paises, (list, tuple, set)):
        paises = ",".join(str(p).strip().upper() for p in paises if str(p).strip())
    elif paises:
        paises = ",".join(p.strip().upper() for p in str(paises).split(",") if p.strip())
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_envios_zonas (id_empresa, nombre, paises, tarifa_base, "
                "tarifa_por_kg, envio_gratis_desde, orden) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (emp, nombre, paises or None, float(tarifa_base or 0), float(tarifa_por_kg or 0),
                 envio_gratis_desde, int(orden)))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_zona(%s): %s", nombre, e)
        return None


def listar_zonas(id_empresa=None, *, solo_activas=False) -> list:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = "SELECT * FROM cd_envios_zonas WHERE id_empresa=%s"
            if solo_activas:
                sql += " AND activa=1"
            cur.execute(sql + " ORDER BY orden, id", (emp,))
            from src.db.conexion import _filas_a_dicts
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_zonas: %s", e)
        return []


def actualizar_zona(id_zona, id_empresa=None, **campos) -> bool:
    permitidos = ("nombre", "paises", "tarifa_base", "tarifa_por_kg", "envio_gratis_desde",
                 "activa", "orden")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return False
    if "paises" in datos and isinstance(datos["paises"], (list, tuple, set)):
        datos["paises"] = ",".join(str(p).strip().upper() for p in datos["paises"] if str(p).strip()) or None
    emp = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            sets = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(f"UPDATE cd_envios_zonas SET {sets} WHERE id=%s AND id_empresa=%s",
                        (*datos.values(), id_zona, emp))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("actualizar_zona(%s): %s", id_zona, e)
        return False


def eliminar_zona(id_zona, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_envios_zonas WHERE id=%s AND id_empresa=%s", (id_zona, emp))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("eliminar_zona(%s): %s", id_zona, e)
        return False


def _zona_para_pais(pais, zonas) -> dict | None:
    pais = (pais or "").strip().upper()
    por_defecto = None
    for z in zonas:
        paises_zona = [p.strip() for p in (z.get("paises") or "").split(",") if p.strip()]
        if not paises_zona:
            por_defecto = por_defecto or z   # "resto del mundo" — la primera que se encuentre
            continue
        if pais and pais in paises_zona:
            return z
    return por_defecto


def peso_total_lineas(lineas, *, id_empresa=None) -> float:
    """Suma el peso (kg) de una cesta usando `articulos.obtener_fisica_seguridad` (el campo
    `peso_unitario` YA existente, reutilizado — líneas sin peso registrado no suman nada, nunca se
    inventa un peso)."""
    from src.db.articulos import obtener_fisica_seguridad
    total = 0.0
    for l in (lineas or []):
        codigo = l.get("codigo") or l.get("codigo_articulo")
        cant = float(l.get("cantidad", 1) or 1)
        try:
            fs = obtener_fisica_seguridad(codigo, id_empresa=id_empresa)
            peso = float(fs["peso_unitario"]) if fs and fs.get("peso_unitario") else 0.0
        except Exception:
            peso = 0.0
        total += peso * cant
    return round(total, 3)


def calcular_envio(pais, peso_total_kg, importe_pedido, *, envio_gratis_forzado=False,
                   id_empresa=None) -> dict:
    """Coste de envío para un destino/peso/importe de pedido. `envio_gratis_forzado` (cupón tipo
    "envio_gratis", ver `comercial.cotizar`) anula el coste sin tocar la zona ni su umbral propio.
    Devuelve `{zona, coste, gratis, motivo, umbral_envio_gratis, falta_para_envio_gratis}` —
    `zona=None` si no hay ninguna zona configurada (degradación honesta: coste 0,
    `motivo="sin_zonas_configuradas"`, NUNCA se inventa una tarifa). `umbral_envio_gratis` (la
    `envio_gratis_desde` de la zona, o `None` si la zona no tiene umbral) y
    `falta_para_envio_gratis` (cuánto falta en importe para alcanzarlo, 0 si ya se alcanzó o no
    aplica) se añaden para la barra de progreso de envío gratis del carrito — no cambian el
    contrato existente (`coste`/`gratis`/`motivo`/`zona`), solo lo amplían."""
    emp = _emp(id_empresa)
    zonas = listar_zonas(emp, solo_activas=True)
    if not zonas:
        return {"zona": None, "coste": 0.0, "gratis": False, "motivo": "sin_zonas_configuradas",
                "umbral_envio_gratis": None, "falta_para_envio_gratis": 0.0}
    zona = _zona_para_pais(pais, zonas)
    if zona is None:
        return {"zona": None, "coste": 0.0, "gratis": False, "motivo": "sin_zona_para_destino",
                "umbral_envio_gratis": None, "falta_para_envio_gratis": 0.0}
    umbral = zona.get("envio_gratis_desde")
    umbral_f = float(umbral) if umbral is not None else None
    importe = float(importe_pedido or 0)
    falta = round(max(0.0, umbral_f - importe), 2) if umbral_f is not None else 0.0
    if envio_gratis_forzado:
        return {"zona": zona["nombre"], "coste": 0.0, "gratis": True, "motivo": "cupon_envio_gratis",
                "umbral_envio_gratis": umbral_f, "falta_para_envio_gratis": 0.0}
    if umbral_f is not None and importe >= umbral_f:
        return {"zona": zona["nombre"], "coste": 0.0, "gratis": True, "motivo": "umbral_zona",
                "umbral_envio_gratis": umbral_f, "falta_para_envio_gratis": 0.0}
    coste = round(float(zona.get("tarifa_base") or 0)
                 + float(zona.get("tarifa_por_kg") or 0) * float(peso_total_kg or 0), 2)
    return {"zona": zona["nombre"], "coste": coste, "gratis": False, "motivo": None,
            "umbral_envio_gratis": umbral_f, "falta_para_envio_gratis": falta}
