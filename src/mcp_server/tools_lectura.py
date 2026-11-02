"""
Tools MCP de SOLO LECTURA (stock, kárdex, reposición, ventas, RFID) — ver `registry.py` para el
contrato de registro/contexto. Reutiliza EXCLUSIVAMENTE motores ya auditados (`services.stock`,
`db.stock_almacen`, `db.kardex`, `services.ia.adaptadores`, `db.ventas_analitica`,
`services.rfid.inventario`) — ninguna query SQL nueva, ningún motor paralelo.

Invariante de seguridad (la MÁS IMPORTANTE de este módulo): TODA consulta se acota explícitamente a
`ctx["id_empresa"]` (el id de empresa resuelto por `transport.py` a partir del JWT validado, nunca
de `argumentos`) — igual que el resto de la REST API. Nunca se deja caer una consulta a la "empresa
de sesión" implícita del proceso servidor.
"""

from __future__ import annotations

import datetime
import decimal
import logging

from src.mcp_server.registry import registrar_tool

logger = logging.getLogger("mcp_server.tools_lectura")


def _normalizar(valor):
    """Convierte recursivamente tipos no JSON-serializables (date/datetime/Decimal) que devuelven
    las capas `db.*` tal cual (no pasan por el `jsonify` de Flask, que sí los maneja) — aquí
    `transport.py` serializa con `json.dumps` estándar, así que hace falta esta conversión."""
    if isinstance(valor, dict):
        return {k: _normalizar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar(v) for v in valor]
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    if isinstance(valor, decimal.Decimal):
        return float(valor)
    return valor


def _limitar(valor, por_defecto, minimo, maximo) -> int:
    try:
        n = int(valor) if valor is not None else por_defecto
    except (TypeError, ValueError):
        n = por_defecto
    return max(minimo, min(n, maximo))


# ── 1. Stock ──────────────────────────────────────────────────────────────────────────────────
def _tool_consultar_stock(ctx: dict, argumentos: dict) -> dict:
    id_empresa = ctx["id_empresa"]
    codigo = str(argumentos.get("codigo") or "").strip()
    if codigo:
        from src.db import stock_almacen as SA
        info = SA.obtener_stock_articulo(codigo, id_empresa=id_empresa)
        return _normalizar({
            "codigo": codigo,
            "stock_total": info.get("total", 0),
            "por_almacen": info.get("detalle", []),
        })

    from src.services import stock as _stock
    q = str(argumentos.get("q") or "")
    id_familia = argumentos.get("id_familia")
    limite = _limitar(argumentos.get("limite"), 50, 1, 200)
    filas = _stock.buscar(id_empresa, q, id_familia=id_familia, limite=limite)
    return _normalizar({"articulos": filas, "total_resultados": len(filas)})


# ── 2. Kárdex / movimientos ───────────────────────────────────────────────────────────────────
def _tool_consultar_movimientos_stock(ctx: dict, argumentos: dict) -> dict:
    from src.db import kardex
    id_empresa = ctx["id_empresa"]
    codigo = str(argumentos.get("codigo") or "").strip() or None
    tipo = str(argumentos.get("tipo") or "").strip() or None
    if tipo and tipo not in kardex.TIPOS:
        raise ValueError(f"Tipo de movimiento desconocido: {tipo}")
    desde = argumentos.get("desde") or None
    hasta = argumentos.get("hasta") or None
    limite = _limitar(argumentos.get("limite"), 100, 1, 500)
    movimientos = kardex.listar_movimientos(
        id_empresa=id_empresa, codigo=codigo, tipo=tipo, desde=desde, hasta=hasta, limite=limite,
    )
    return _normalizar({"movimientos": movimientos, "total": len(movimientos)})


# ── 3. Alertas de reposición ──────────────────────────────────────────────────────────────────
def _tool_consultar_alertas_reposicion(ctx: dict, argumentos: dict) -> dict:
    from src.services.ia import adaptadores
    id_empresa = ctx["id_empresa"]
    alertas = adaptadores.articulos_bajo_umbral(id_empresa=id_empresa)
    return _normalizar({"alertas": alertas, "total": len(alertas)})


# ── 4. Resumen de ventas (rango arbitrario) ───────────────────────────────────────────────────
def _tool_resumen_ventas(ctx: dict, argumentos: dict) -> dict:
    from src.db import ventas_analitica as va
    id_empresa = ctx["id_empresa"]
    desde = argumentos.get("desde")
    hasta = argumentos.get("hasta")
    if not desde or not hasta:
        raise ValueError("Los parámetros 'desde' y 'hasta' son obligatorios (fechas ISO YYYY-MM-DD).")
    seccion = argumentos.get("seccion") or None
    id_tienda = argumentos.get("id_tienda")
    filas = va.serie_por_dia(desde, hasta, secc=seccion, id_empresa=id_empresa, id_tienda=id_tienda)
    puntos = [{"fecha": f[0], "total": round(float(f[1] or 0), 2)} for f in filas]
    total_periodo = round(sum(p["total"] for p in puntos), 2)
    return _normalizar({
        "desde": desde, "hasta": hasta, "seccion": seccion, "id_tienda": id_tienda,
        "puntos": puntos, "total_periodo": total_periodo, "dias_con_datos": len(puntos),
    })


# ── 5. Estado RFID ────────────────────────────────────────────────────────────────────────────
def _tool_estado_rfid(ctx: dict, argumentos: dict) -> dict:
    from src.services.rfid.inventario import barrido_inventario
    id_empresa = ctx["id_empresa"]
    id_tienda = argumentos.get("id_tienda")
    incluir_sin_stock = bool(argumentos.get("incluir_sin_stock") or False)
    limite_detalle = _limitar(argumentos.get("limite_detalle"), 20, 1, 100)

    resultado = barrido_inventario(id_empresa, id_tienda, incluir_sin_stock=incluir_sin_stock)
    es_simulado = resultado["modo"] == "SIMULADO"
    return _normalizar({
        "modo": resultado["modo"],
        "hardware_real": not es_simulado,
        "nota": (
            "SIMULADO: no hay un lector RFID Zebra físico conectado a este backend; estos datos "
            "son una SIMULACIÓN realista (mismo motor que usa el barrido de inventario de "
            "escritorio), NO una lectura de hardware en vivo."
            if es_simulado else
            "Lectura real de hardware RFID Zebra."
        ),
        "total_articulos": resultado["total_articulos"],
        "total_unidades": resultado["total_unidades"],
        "discrepancias": resultado["discrepancias"],
        "detectados": resultado["detectados"][:limite_detalle],
    })


def registrar_herramientas_lectura() -> None:
    """Da de alta las tools MCP de solo lectura (stock/kárdex/reposición/ventas/RFID). Se invoca
    una vez desde `registry._cargar_tools_incorporadas()`."""
    from src.db import kardex

    registrar_tool(
        "consultar_stock",
        "Consulta niveles de stock. Si se indica 'codigo', devuelve el desglose EXACTO de ese "
        "artículo por almacén/tienda (stock_total + por_almacen: lista de {id_almacen, nombre, "
        "tipo_almacen, id_tienda, cantidad}). Si no se indica 'codigo', busca artículos por texto "
        "libre ('q': código o nombre, coincidencia parcial) y/o por familia/categoría "
        "('id_familia'), devolviendo una lista de artículos con sus niveles de "
        "stock_tienda/stock_total/stock_central. Resultados siempre acotados a la empresa del "
        "usuario autenticado.",
        {
            "type": "object",
            "properties": {
                "codigo": {"type": "string",
                           "description": "Código exacto del artículo para el desglose por "
                                          "almacén. Si se indica, ignora 'q'/'id_familia'."},
                "q": {"type": "string",
                      "description": "Texto libre a buscar en el código o el nombre del artículo."},
                "id_familia": {"type": "integer",
                               "description": "Filtra por id de familia/categoría de artículo. "
                                              "Usa 0 para artículos sin familia asignada."},
                "limite": {"type": "integer", "minimum": 1, "maximum": 200,
                           "description": "Máximo de artículos a devolver en la búsqueda por "
                                          "texto (por defecto 50)."},
            },
            "additionalProperties": False,
        },
        _tool_consultar_stock,
    )

    registrar_tool(
        "consultar_movimientos_stock",
        "Devuelve el historial de movimientos de kárdex (entradas/salidas/traspasos/mermas/"
        "ajustes/producción/...) de la empresa del usuario autenticado, en orden cronológico "
        "descendente. Permite filtrar por artículo ('codigo'), por tipo de movimiento ('tipo') y "
        "por rango de fechas ('desde'/'hasta', ISO YYYY-MM-DD). Cada movimiento incluye cantidad, "
        "fecha, usuario, origen/destino y el stock antes/después cuando está disponible.",
        {
            "type": "object",
            "properties": {
                "codigo": {"type": "string",
                           "description": "Código del artículo. Si se omite, incluye todos los "
                                          "artículos de la empresa."},
                "tipo": {"type": "string", "enum": list(kardex.TIPOS),
                         "description": "Filtra por tipo de movimiento de kárdex."},
                "desde": {"type": "string",
                          "description": "Fecha ISO (YYYY-MM-DD) desde la que listar (inclusive)."},
                "hasta": {"type": "string",
                          "description": "Fecha ISO (YYYY-MM-DD) hasta la que listar (inclusive)."},
                "limite": {"type": "integer", "minimum": 1, "maximum": 500,
                           "description": "Máximo de movimientos a devolver (por defecto 100)."},
            },
            "additionalProperties": False,
        },
        _tool_consultar_movimientos_stock,
    )

    registrar_tool(
        "consultar_alertas_reposicion",
        "Devuelve las alertas de reposición VIGENTES AHORA MISMO: artículos cuyo stock en tienda "
        "ha caído por debajo del 70% de su objetivo ('Stock_esperado') y que SÍ tienen stock "
        "disponible en almacén para reponer (misma regla que usa el Informe de Reposición de "
        "escritorio). Cada alerta incluye código, nombre, stock_tienda, stock_almacen, objetivo y "
        "unidades que faltan. No admite parámetros; siempre se acota a la empresa del usuario "
        "autenticado.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        _tool_consultar_alertas_reposicion,
    )

    registrar_tool(
        "resumen_ventas",
        "Resumen de ventas facturadas en un RANGO DE FECHAS ARBITRARIO (a diferencia del endpoint "
        "REST móvil, que solo ofrece hoy/semana/mes). Devuelve una serie temporal diaria — lista "
        "de puntos {fecha, total} — lista para construir una gráfica, además del total agregado "
        "del período ('total_periodo'). Admite filtrar por sección/departamento de venta "
        "('seccion') y, opcionalmente, por una tienda concreta ('id_tienda'); si se omite "
        "'id_tienda', agrega todas las tiendas de la empresa. Acotado siempre a la empresa del "
        "usuario autenticado.",
        {
            "type": "object",
            "properties": {
                "desde": {"type": "string",
                          "description": "Fecha ISO (YYYY-MM-DD) de inicio del rango (inclusive). "
                                         "Obligatorio."},
                "hasta": {"type": "string",
                          "description": "Fecha ISO (YYYY-MM-DD) de fin del rango (inclusive). "
                                         "Obligatorio."},
                "seccion": {"type": "string",
                            "description": "Filtra por sección/departamento de venta. Si se "
                                           "omite, agrega todas las secciones."},
                "id_tienda": {"type": "integer",
                              "description": "Filtra por el id interno de una tienda concreta. Si "
                                             "se omite, agrega todas las tiendas de la empresa."},
            },
            "required": ["desde", "hasta"],
            "additionalProperties": False,
        },
        _tool_resumen_ventas,
    )

    registrar_tool(
        "estado_rfid",
        "Estado ACTUAL de monitorización RFID/estanterías de la empresa: ejecuta un barrido y "
        "devuelve el conteo detectado por artículo frente al stock esperado (discrepancias "
        "primero). El campo 'modo' indica HONESTAMENTE el origen del dato: 'RFID' si hay un "
        "lector Zebra físico conectado, o 'SIMULADO' si no lo hay (caso habitual en este backend, "
        "que no tiene acceso directo al hardware del puesto de escritorio) — 'hardware_real' y "
        "'nota' lo dejan explícito para no presentar NUNCA una simulación como una lectura en "
        "vivo real.",
        {
            "type": "object",
            "properties": {
                "id_tienda": {"type": "integer",
                              "description": "Tienda a inspeccionar. Si se omite, usa el almacén/"
                                             "tienda por defecto de la empresa."},
                "incluir_sin_stock": {"type": "boolean",
                                      "description": "Si es true, incluye también artículos sin "
                                                     "stock esperado (por defecto false)."},
                "limite_detalle": {"type": "integer", "minimum": 1, "maximum": 100,
                                  "description": "Máximo de artículos detallados a devolver en "
                                                 "'detectados' (por defecto 20; las "
                                                 "discrepancias se listan primero)."},
            },
            "additionalProperties": False,
        },
        _tool_estado_rfid,
    )


__all__ = ["registrar_herramientas_lectura"]
