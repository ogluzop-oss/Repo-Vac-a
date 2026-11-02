"""
Ejecutor de delegación — CRM: generar un borrador de presupuesto para un cliente a partir de una
breve descripción de lo que pide. SOMA SOLO puede elegir artículos reales de la empresa (se le
pasa una lista de candidatos obtenida por búsqueda de texto real sobre `articulos`; nunca se le
deja inventar un código) — grounding obligatorio, mismo criterio de honestidad que el resto de
asistentes IA de la app. Reutiliza `db.ventas_comercial.crear_presupuesto` (el ÚNICO CRUD de
presupuestos VTA.6 ya existente): el presupuesto se crea SIEMPRE en estado 'borrador', pendiente
de la aprobación humana habitual (`aprobar_presupuesto`) — nunca se compromete nada sin revisión.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("soma_delegacion.ejecutores.crm")

_MAX_CANDIDATOS = 25


_PALABRAS_VACIAS = {"de", "la", "el", "los", "las", "un", "una", "unos", "unas", "para", "con",
                    "por", "en", "del", "al", "y", "o", "que", "quiero", "necesito", "pide",
                    "pida", "cliente"}


def _candidatos_articulos(texto, id_empresa):
    """Búsqueda de texto sobre `articulos` de ESTA empresa — el único universo del que SOMA
    puede elegir líneas (nunca se consulta ni se expone stock/precio de otra empresa). El brief
    es lenguaje natural ("2 sillas de oficina para la sala de reuniones"), así que se busca por
    CADA palabra significativa (≥4 letras, sin vacías de relleno) en vez de por la frase
    completa — una coincidencia exacta de la frase entera casi nunca encontraría nada real."""
    palabras = [p for p in (texto or "").lower().split()
               if len(p) >= 4 and p not in _PALABRAS_VACIAS]
    if not palabras:
        palabras = [(texto or "").strip()] if (texto or "").strip() else []
    if not palabras:
        return []
    condiciones = " OR ".join(["codigo LIKE %s OR nombre LIKE %s"] * len(palabras))
    params = [id_empresa]
    for p in palabras:
        like = f"%{p}%"
        params += [like, like]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT codigo, nombre, COALESCE(precio,0) FROM articulos WHERE id_empresa=%s "
                f"AND ({condiciones}) ORDER BY nombre LIMIT %s",
                (*params, _MAX_CANDIDATOS))
            filas = cur.fetchall()
    except Exception as e:
        logger.error("_candidatos_articulos: %s", e)
        return []
    out = []
    for f in filas:
        if isinstance(f, dict):
            out.append({"codigo": f.get("codigo"), "nombre": f.get("nombre"),
                       "precio": float(f.get("precio") or 0)})
        else:
            out.append({"codigo": f[0], "nombre": f[1], "precio": float(f[2] or 0)})
    return out


def ejecutar_generar_presupuesto(regla: dict, contexto: dict, *, id_empresa, usuario=None) -> dict:
    """`contexto` esperado: {"id_cliente": int, "brief": str}."""
    from src.services.soma_delegacion.motor import MOTIVOS_LEGIBLES, preguntar_soma

    brief = (contexto.get("brief") or "").strip()
    if not brief:
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": "Falta describir lo que pide el cliente."}

    candidatos = _candidatos_articulos(brief, id_empresa)
    if not candidatos:
        return {"ok": True, "estado": "descartado", "decision": None,
               "detalle": "No se encontró ningún artículo de la empresa que coincida con la "
                         "petición — SOMA no puede proponer líneas sin artículos reales."}

    catalogo_txt = "\n".join(f"- {c['codigo']}: {c['nombre']} ({c['precio']:.2f} €)"
                             for c in candidatos)
    prompt = (
        "Eres SOMA, el asistente de IA de un ERP, generando un BORRADOR de presupuesto comercial "
        "para un cliente. SOLO puedes usar los artículos de la lista de abajo (nunca inventes un "
        "código que no esté en ella) y debes seguir las instrucciones del administrador sobre "
        "cómo construir presupuestos (descuentos, exclusiones, observaciones a añadir…).\n\n"
        f"Instrucciones del administrador:\n\"\"\"\n{regla.get('instrucciones', '')}\n\"\"\"\n\n"
        f"Lo que pide el cliente:\n\"\"\"\n{brief}\n\"\"\"\n\n"
        f"Artículos disponibles (código: nombre (precio de lista)):\n{catalogo_txt}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON, sin texto adicional: "
        '{"lineas": [{"codigo": "...", "cantidad": numero, "precio_unitario": numero}], '
        '"observaciones": "texto breve para el presupuesto"}. '
        "Si ningún artículo de la lista encaja razonablemente con lo que pide el cliente, "
        'devuelve {"lineas": [], "observaciones": "motivo por el que no se pudo generar"}.'
    )
    r = preguntar_soma(prompt, id_empresa=id_empresa, usuario=usuario, tarea="soma_delegacion_crm")
    if not r.get("ok"):
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": MOTIVOS_LEGIBLES.get(r.get("motivo"), "No se pudo generar el presupuesto.")}

    datos = r["datos"]
    codigos_validos = {c["codigo"] for c in candidatos}
    precios = {c["codigo"]: c["precio"] for c in candidatos}
    lineas_in = datos.get("lineas") or []
    lineas = []
    for ln in lineas_in:
        codigo = ln.get("codigo")
        if codigo not in codigos_validos:
            continue   # nunca se cuela un código que SOMA se haya inventado
        try:
            cantidad = max(1, int(ln.get("cantidad") or 1))
        except (TypeError, ValueError):
            cantidad = 1
        try:
            precio = float(ln.get("precio_unitario"))
        except (TypeError, ValueError):
            precio = precios.get(codigo, 0.0)
        lineas.append({"codigo_articulo": codigo, "descripcion": codigo, "cantidad": cantidad,
                       "precio_unitario": precio})

    if not lineas:
        return {"ok": True, "estado": "descartado", "decision": datos,
               "detalle": datos.get("observaciones") or
                         "SOMA no encontró artículos adecuados para esta petición."}

    from src.db import ventas_comercial as VC
    id_usuario = (usuario or {}).get("nombre") or (usuario or {}).get("id")
    did = VC.crear_presupuesto(id_cliente=contexto.get("id_cliente"), lineas=lineas,
                               observaciones=(datos.get("observaciones") or "")[:500],
                               usuario=f"SOMA (delegado por {id_usuario})" if id_usuario else "SOMA",
                               id_empresa=id_empresa)
    if not did:
        return {"ok": False, "estado": "error", "decision": datos,
               "detalle": "No se pudo guardar el presupuesto."}
    return {"ok": True, "estado": "aplicado", "decision": datos,
           "detalle": f"Presupuesto #{did} creado en borrador, pendiente de tu aprobación."}
