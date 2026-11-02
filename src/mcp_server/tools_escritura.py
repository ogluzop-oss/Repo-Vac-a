"""
Tools MCP de ESCRITURA — ver `registry.py` para el contrato de registro/contexto y
`tools_lectura.py` para el patrón de referencia (acceso a `ctx`, normalización JSON, convención
de registro). Reutiliza EXCLUSIVAMENTE motores ya auditados: `services.automatizacion.acciones`
(propuestas de reposición, el mismo camino que usa el Copiloto SOMA vía
`services.copilot.acciones.solicitar`), `db.reabastecimiento`, `db.catalogo` (PIM) y `db.articulos`
— ninguna query SQL nueva, ningún motor paralelo.

Invariante de seguridad (igual que `tools_lectura.py`): TODA operación se acota explícitamente a
`ctx["id_empresa"]` (resuelto por `transport.py` a partir del JWT validado, nunca de
`argumentos`). Cualquier id referenciado por el llamador externo (artículo, categoría, marca,
proveedor) se VERIFICA que pertenece a esa empresa antes de usarse — nunca se confía en un id
ajeno sin comprobar.

Gobernanza (recordatorio, ver `registry.py`/CLAUDE.md): SOMA es un orquestador basado en reglas
que NUNCA ejecuta acciones directamente.

- `crear_borrador_pedido_compra` enruta SIEMPRE a través de
  `services.automatizacion.acciones.crear_propuesta_compra` (la misma función que usa
  `services.copilot.acciones.solicitar` cuando un usuario le pide a SOMA un pedido/reposición) —
  crea una fila en `reab_propuestas` con `estado='pendiente'`, NUNCA un pedido ejecutado. Requiere
  aprobación humana en Workflow/Gobierno (módulo de Reposición) para convertirse en un pedido de
  compra real (`db.reabastecimiento.generar_pedidos_compra`).
- `gestionar_articulo_catalogo` opera sobre el PIM (`db.catalogo`: fichas de catálogo web y
  categorías) — a diferencia de los pedidos de compra, hoy NO existe un paso de aprobación
  Workflow/Gobierno para altas/ediciones de catálogo (la propia GUI de escritorio,
  `gui/catalogo_gestion.py`, escribe directamente vía `cat.upsert_producto`/`crear_categoria`/
  `actualizar_categoria` sin pasar por ninguna propuesta). En vez de inventar un motor de
  propuestas paralelo para esto, esta tool reutiliza el mecanismo de "borrador" que la propia
  tabla YA tiene: toda ficha/categoría CREADA desde MCP nace OCULTA (no se expone nunca
  `visible_web`/`visible` como campo editable por esta vía) — un humano debe revisarla y
  publicarla desde Catálogo/Canal Web. Esto da, con cero infraestructura nueva, la misma garantía
  de "nada se publica sin un humano" que pide la gobernanza de SOMA, proporcionada a una
  superficie (catálogo) que no tenía ese control antes. Tampoco da de alta artículos NUEVOS de
  inventario (`articulos`): solo gestiona la ficha de catálogo de un artículo que YA existe en el
  almacén de la empresa — dar de alta un SKU nuevo sigue siendo responsabilidad exclusiva de
  Recepción/Compras en el escritorio.
"""

from __future__ import annotations

import logging

from src.mcp_server.registry import registrar_tool
from src.mcp_server.tools_lectura import _normalizar

logger = logging.getLogger("mcp_server.tools_escritura")


# ── Helpers de verificación de pertenencia a la empresa (defense-in-depth, mismo criterio que
#    el resto del sistema: nunca confiar en un id ajeno sin comprobar su id_empresa real) ──
def _verificar_categoria(id_categoria, id_empresa) -> None:
    if id_categoria is None:
        return
    from src.db.conexion import obtener_conexion
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM catalogo_categorias WHERE id=%s AND id_empresa=%s",
                    (id_categoria, id_empresa))
        if not cur.fetchone():
            raise ValueError(f"La categoría #{id_categoria} no existe en esta empresa.")


def _verificar_marca(id_marca, id_empresa) -> None:
    if id_marca is None:
        return
    from src.db.conexion import obtener_conexion
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM catalogo_marcas WHERE id=%s AND id_empresa=%s",
                    (id_marca, id_empresa))
        if not cur.fetchone():
            raise ValueError(f"La marca #{id_marca} no existe en esta empresa.")


# ── 1. Borrador de pedido de compra (propuesta de reposición, PENDIENTE DE APROBACIÓN) ──────────
def _tool_crear_borrador_pedido_compra(ctx: dict, argumentos: dict) -> dict:
    from src.db import articulos as ART
    from src.db import proveedores as PROV
    from src.db import reabastecimiento as REAB
    from src.services.automatizacion import acciones as AUTO

    id_empresa = ctx["id_empresa"]
    codigo = str(argumentos.get("codigo_articulo") or "").strip()
    if not codigo:
        raise ValueError("'codigo_articulo' es obligatorio.")
    if not ART.existe_codigo(codigo, id_empresa=id_empresa):
        raise ValueError(f"El artículo '{codigo}' no existe en esta empresa.")

    # Verificación de pertenencia del proveedor (si se indica) — nunca se confía en un
    # id_proveedor ajeno sin comprobar que pertenece a la empresa autenticada.
    id_proveedor = argumentos.get("id_proveedor")
    proveedor = None
    if id_proveedor is not None:
        proveedor = PROV.obtener_proveedor(id_proveedor, id_empresa=id_empresa)
        if not proveedor:
            raise ValueError(f"El proveedor #{id_proveedor} no existe en esta empresa.")

    info_stock = ART.obtener_stock(codigo, id_empresa=id_empresa) or {}
    nombre = info_stock.get("nombre") or codigo
    stock_tienda = int(info_stock.get("lineal") or 0)
    objetivo = int(info_stock.get("esperado") or 0)

    cantidad = argumentos.get("cantidad")
    if cantidad is None:
        # Sin cantidad explícita: usa el mismo cálculo que las alertas de reposición
        # (`consultar_alertas_reposicion` / informe de reposición de escritorio).
        dato = next((a for a in REAB.articulos_bajo_umbral(id_empresa=id_empresa)
                    if a["codigo"] == codigo), None)
        if dato:
            cantidad = dato["cantidad"]
            objetivo = dato["stock_objetivo"]
        else:
            cantidad = 1
    cantidad = max(1, int(cantidad))

    ya_existia = REAB.propuesta_pendiente_existe(codigo, id_empresa=id_empresa)

    item = {"codigo": codigo, "nombre": nombre, "faltan": cantidad,
            "stock_tienda": stock_tienda, "objetivo": objetivo}
    resultado_motor = AUTO.crear_propuesta_compra({"items": [item]}, None, id_empresa)

    pendientes = REAB.listar_propuestas(("pendiente",), id_empresa=id_empresa)
    propuesta = next((p for p in pendientes if p["codigo"] == codigo), None)

    motivo = str(argumentos.get("motivo") or "").strip() or None
    ref = f"#{propuesta['id']}" if propuesta else "(sin id — revisar listado de propuestas)"

    return _normalizar({
        "estado": "PENDIENTE_APROBACION",
        "ya_existia_pendiente": ya_existia,
        "propuesta": propuesta,
        "codigo_articulo": codigo,
        "cantidad_solicitada": cantidad,
        "id_proveedor_sugerido": id_proveedor,
        "proveedor_verificado": (proveedor or {}).get("razon_social"),
        "motivo": motivo,
        "nota_proveedor_motivo": (
            "id_proveedor/motivo se han verificado pero el motor de propuestas de reposición "
            "NO tiene columnas para persistirlos en la propuesta hoy; quedan solo como "
            "referencia en esta respuesta — un humano los asignará al convertir la propuesta "
            "en un pedido de compra real." if (id_proveedor or motivo) else None
        ),
        "mensaje_para_humano": (
            f"Ha quedado un BORRADOR pendiente de aprobación en Smart Manager, referencia "
            f"{ref}, para '{nombre}' ({codigo}), cantidad {cantidad}. NO es un pedido realizado "
            "ni confirmado — requiere aprobación humana en Workflow/Gobierno (módulo de "
            "Reposición) antes de convertirse en un pedido de compra real."
        ),
        "resultado_motor": resultado_motor,
    })


# ── 2. Gestión de ficha de catálogo (producto/categoría) — ver nota de gobernanza arriba ───────
_CAMPOS_PRODUCTO_MCP = ("id_categoria", "id_marca", "titulo_web", "descripcion_web",
                        "orden", "seo_title", "seo_descripcion")
_CAMPOS_CATEGORIA_MCP = ("nombre", "parent_id", "descripcion", "imagen", "orden")


def _tool_gestionar_articulo_catalogo(ctx: dict, argumentos: dict) -> dict:
    from src.db import articulos as ART
    from src.db import catalogo as CAT

    id_empresa = ctx["id_empresa"]
    accion = str(argumentos.get("accion") or "").strip()

    if accion == "crear_categoria":
        nombre = str(argumentos.get("nombre") or "").strip()
        if not nombre:
            raise ValueError("'nombre' es obligatorio para accion='crear_categoria'.")
        parent_id = argumentos.get("parent_id")
        _verificar_categoria(parent_id, id_empresa)
        id_categoria = CAT.crear_categoria(
            nombre, parent_id=parent_id, descripcion=argumentos.get("descripcion"),
            imagen=argumentos.get("imagen"), orden=int(argumentos.get("orden") or 0),
            id_empresa=id_empresa,
        )
        if not id_categoria:
            raise RuntimeError("No se pudo crear la categoría.")
        # Gobernanza: el esquema de `catalogo_categorias` nace con visible=1 POR DEFECTO
        # (columna NOT NULL DEFAULT 1) y `crear_categoria` no admite 'visible' en el INSERT —
        # se fuerza explícitamente a oculta aquí (nunca confiar en el default de la tabla).
        CAT.actualizar_categoria(id_categoria, id_empresa=id_empresa, visible=0)
        return _normalizar({
            "accion": "crear_categoria", "id_categoria": id_categoria, "nombre": nombre,
            "visible": False,
            "mensaje_para_humano": (
                f"Categoría '{nombre}' creada (#{id_categoria}), OCULTA por defecto "
                "(visible=0). Un humano debe revisarla y publicarla desde Catálogo."
            ),
        })

    if accion == "editar_categoria":
        id_categoria = argumentos.get("id_categoria")
        if not id_categoria:
            raise ValueError("'id_categoria' es obligatorio para accion='editar_categoria'.")
        _verificar_categoria(id_categoria, id_empresa)
        campos = {k: argumentos[k] for k in _CAMPOS_CATEGORIA_MCP if k in argumentos}
        if not campos:
            raise ValueError("No se indicó ningún campo a editar (nombre/parent_id/"
                             "descripcion/imagen/orden).")
        if "parent_id" in campos:
            _verificar_categoria(campos["parent_id"], id_empresa)
        ok = CAT.actualizar_categoria(id_categoria, id_empresa=id_empresa, **campos)
        return _normalizar({
            "accion": "editar_categoria", "id_categoria": id_categoria, "ok": bool(ok),
            "campos_actualizados": list(campos.keys()),
            "mensaje_para_humano": (
                f"Categoría #{id_categoria} actualizada." if ok else
                f"No se pudo actualizar la categoría #{id_categoria} (¿no pertenece a esta "
                "empresa?)."
            ),
        })

    if accion in ("crear_producto", "editar_producto"):
        codigo = str(argumentos.get("codigo_articulo") or "").strip()
        if not codigo:
            raise ValueError("'codigo_articulo' es obligatorio.")
        if not ART.existe_codigo(codigo, id_empresa=id_empresa):
            raise ValueError(
                f"El artículo '{codigo}' no existe en el inventario de esta empresa. Esta tool "
                "gestiona la FICHA DE CATÁLOGO WEB de un artículo ya existente — no da de alta "
                "artículos nuevos de almacén (eso sigue siendo responsabilidad de Recepción/"
                "Compras en el escritorio)."
            )
        campos = {k: argumentos[k] for k in _CAMPOS_PRODUCTO_MCP if k in argumentos}
        if "id_categoria" in campos:
            _verificar_categoria(campos["id_categoria"], id_empresa)
        if "id_marca" in campos:
            _verificar_marca(campos["id_marca"], id_empresa)

        existente = CAT.obtener_producto(codigo_articulo=codigo, id_empresa=id_empresa)
        if accion == "crear_producto" and existente:
            raise ValueError(f"Ya existe una ficha de catálogo para '{codigo}' (#"
                             f"{existente['id']}); usa accion='editar_producto'.")
        if accion == "editar_producto" and not existente:
            raise ValueError(f"No existe ficha de catálogo para '{codigo}' todavía; usa "
                             "accion='crear_producto'.")

        if accion == "crear_producto":
            # Gobernanza: el esquema de `catalogo_productos` nace con visible_web=1 POR
            # DEFECTO (columna NOT NULL DEFAULT 1) — se fuerza explícitamente a oculto en el
            # alta (nunca confiar en el default de la tabla); en la edición no se toca.
            campos["visible_web"] = 0
        id_producto = CAT.upsert_producto(codigo, id_empresa=id_empresa, **campos)
        if not id_producto:
            raise RuntimeError("No se pudo guardar la ficha de catálogo.")

        if accion == "crear_producto":
            mensaje = (f"Ficha de catálogo creada para '{codigo}' (#{id_producto}), OCULTA por "
                      "defecto (visible_web=0). Un humano debe revisarla y publicarla desde "
                      "Catálogo/Canal Web.")
        else:
            mensaje = (f"Ficha de catálogo de '{codigo}' (#{id_producto}) actualizada. La "
                      "visibilidad web no se modifica desde esta vía — se gestiona solo desde "
                      "Catálogo/Canal Web.")
        return _normalizar({
            "accion": accion, "id_producto": id_producto, "codigo_articulo": codigo,
            "visible": False if accion == "crear_producto" else None,
            "campos_actualizados": list(campos.keys()),
            "mensaje_para_humano": mensaje,
        })

    raise ValueError(
        f"accion desconocida: {accion!r}. Debe ser una de: crear_producto, editar_producto, "
        "crear_categoria, editar_categoria."
    )


def registrar_herramientas_escritura() -> None:
    """Da de alta las tools MCP de escritura (borrador de pedido de compra / gestión de ficha de
    catálogo). Se invoca una vez desde `registry._cargar_tools_incorporadas()`."""

    registrar_tool(
        "crear_borrador_pedido_compra",
        "Crea un BORRADOR/PROPUESTA de pedido de compra (reposición de stock) PENDIENTE DE "
        "APROBACIÓN HUMANA en Smart Manager — reutiliza EXACTAMENTE el mismo motor de "
        "propuestas que usa el Copiloto SOMA cuando un usuario le pide un pedido/reposición "
        "(`AutomationService` → tabla de propuestas, estado 'pendiente'). ESTO NUNCA CREA NI "
        "EJECUTA UN PEDIDO REAL: la propuesta debe ser revisada y aprobada por un humano en "
        "Workflow/Gobierno (módulo de Reposición) de Smart Manager antes de convertirse en un "
        "pedido de compra real. Si ya existe una propuesta pendiente para ese artículo, no "
        "duplica — reutiliza la existente. El artículo debe existir ya en el inventario de la "
        "empresa autenticada; si se indica 'id_proveedor', se verifica que pertenezca a esa "
        "misma empresa (se rechaza si no).",
        {
            "type": "object",
            "properties": {
                "codigo_articulo": {
                    "type": "string",
                    "description": "Código del artículo a reponer. Debe existir ya en el "
                                   "inventario de la empresa autenticada. Obligatorio.",
                },
                "cantidad": {
                    "type": "integer", "minimum": 1,
                    "description": "Cantidad a solicitar en el borrador. Si se omite, se "
                                   "calcula automáticamente con el mismo motor que las alertas "
                                   "de reposición (objetivo de stock menos stock actual); si el "
                                   "artículo no tiene alerta vigente, usa 1 por defecto.",
                },
                "id_proveedor": {
                    "type": "integer",
                    "description": "Id de proveedor sugerido para esta reposición. Se verifica "
                                   "que pertenezca a la empresa autenticada (se rechaza si no). "
                                   "Informativo: el motor de propuestas actual no tiene un "
                                   "campo para persistirlo en la propuesta; un humano lo "
                                   "asignará al convertirla en pedido.",
                },
                "motivo": {
                    "type": "string",
                    "description": "Motivo o comentario libre sobre esta solicitud de "
                                   "reposición. Informativo únicamente (se devuelve en la "
                                   "respuesta, no se persiste en la propuesta hoy).",
                },
            },
            "required": ["codigo_articulo"],
            "additionalProperties": False,
        },
        _tool_crear_borrador_pedido_compra,
        requiere_confirmacion=True,
    )

    registrar_tool(
        "gestionar_articulo_catalogo",
        "Crea o edita una FICHA DE CATÁLOGO WEB (producto) o una CATEGORÍA del PIM de Smart "
        "Manager (`db.catalogo` — overlay comercial sobre un artículo YA existente en el "
        "inventario: no da de alta artículos nuevos de almacén). Acción vía el parámetro "
        "'accion': 'crear_producto'/'editar_producto' (ficha de catálogo de un artículo) o "
        "'crear_categoria'/'editar_categoria'. GOBERNANZA: toda ficha/categoría CREADA desde "
        "esta tool nace SIEMPRE OCULTA (no visible en la web) — esta tool JAMÁS puede publicarla "
        "ni cambiar su visibilidad; un humano debe revisarla y publicarla manualmente desde "
        "Catálogo/Canal Web en Smart Manager. Esto es intencional: a diferencia de un pedido de "
        "compra, el catálogo no tiene hoy un flujo de aprobación Workflow/Gobierno, así que esta "
        "tool usa el propio campo de visibilidad de la tabla como mecanismo de borrador en vez "
        "de inventar un motor de propuestas paralelo. Toda categoría/marca referenciada se "
        "verifica que pertenezca a la empresa autenticada (se rechaza si no).",
        {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["crear_producto", "editar_producto", "crear_categoria",
                             "editar_categoria"],
                    "description": "Operación a realizar.",
                },
                "codigo_articulo": {
                    "type": "string",
                    "description": "Código del artículo (debe existir ya en el inventario de la "
                                   "empresa). Obligatorio para 'crear_producto'/"
                                   "'editar_producto'.",
                },
                "id_categoria": {
                    "type": "integer",
                    "description": "Para 'editar_categoria': id de la categoría a editar "
                                   "(obligatorio). Para 'crear_producto'/'editar_producto': "
                                   "categoría a asignar a la ficha de catálogo (debe pertenecer "
                                   "a la empresa).",
                },
                "id_marca": {
                    "type": "integer",
                    "description": "Marca a asignar a la ficha de catálogo (debe pertenecer a "
                                   "la empresa). Solo para 'crear_producto'/'editar_producto'.",
                },
                "titulo_web": {"type": "string",
                               "description": "Título comercial para la web."},
                "descripcion_web": {"type": "string",
                                    "description": "Descripción comercial para la web."},
                "seo_title": {"type": "string", "description": "Título SEO."},
                "seo_descripcion": {"type": "string", "description": "Descripción SEO."},
                "orden": {"type": "integer",
                         "description": "Orden de aparición (producto o categoría)."},
                "nombre": {"type": "string",
                          "description": "Nombre de la categoría. Obligatorio para "
                                         "'crear_categoria'."},
                "parent_id": {"type": "integer",
                             "description": "Categoría padre (debe pertenecer a la empresa). "
                                            "Para 'crear_categoria'/'editar_categoria'."},
                "descripcion": {"type": "string", "description": "Descripción de la categoría."},
                "imagen": {"type": "string",
                          "description": "URL/ruta de imagen de la categoría."},
            },
            "required": ["accion"],
            "additionalProperties": False,
        },
        _tool_gestionar_articulo_catalogo,
        requiere_confirmacion=True,
    )


__all__ = ["registrar_herramientas_escritura"]
