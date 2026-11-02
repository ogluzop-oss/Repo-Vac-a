"""
Carteles/Folletos publicitarios — 4ª pestaña del módulo Proyectos. CRUD del diseño (ligado a un
proyecto, igual patrón que `proyecto_tareas`/`proyecto_horas`/`proyecto_costes`), catálogo de
formatos estándar, generación de miniatura/exportación (delega en `render_cartel`, headless) y
borrador asistido por IA (reutiliza el MISMO cliente Anthropic degradable de SOMA —
`copilot.motor_llm._cliente`/`_MODELO` — y el mismo chokepoint medido/auditado
`ia_control_uso.ejecutar_tarea_ia` que ya usa `catalogo.ia_contenido`; un solo turno, sin
herramientas ni historial, igual criterio).

Nota honesta: el encargo original mencionaba una integración opcional con "Google Gemini Nano
Banana" — auditado el repositorio, esa integración NO EXISTE en ningún sitio (no hay cliente, ni
clave, ni dependencia). No se inventa aquí: `generar_copy_ia` usa únicamente Anthropic (vía
SOMA), con degradación honesta si no hay clave configurada — igual que el resto de asistentes IA
de la app.
"""

import json
import logging
import os

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("proyectos.carteles")

# ── Catálogo de formatos estándar (ancho x alto en mm, orientación NATURAL/portrait) ──────────
FORMATOS = {
    "folleto_a4_ficha":    {"tipo": "folleto", "ancho_mm": 210, "alto_mm": 297, "modo": None,
                            "etiqueta": "A4 (21 x 29.7 cm) - Ficha sencilla"},
    "folleto_a4_diptico":  {"tipo": "folleto", "ancho_mm": 210, "alto_mm": 297, "modo": "diptico",
                            "etiqueta": "A4 - Díptico (plegado central)"},
    "folleto_a4_triptico": {"tipo": "folleto", "ancho_mm": 210, "alto_mm": 297, "modo": "triptico",
                            "etiqueta": "A4 - Tríptico (3 columnas de plegado)"},
    "folleto_a5":          {"tipo": "folleto", "ancho_mm": 148, "alto_mm": 210, "modo": None,
                            "etiqueta": "A5 (14.8 x 21 cm) - Volante / Flyer"},
    "folleto_dl":          {"tipo": "folleto", "ancho_mm": 100, "alto_mm": 210, "modo": None,
                            "etiqueta": "DL / Formato Americano (10 x 21 cm) - Encarte / Menú"},
    "cartel_a3":           {"tipo": "cartel", "ancho_mm": 297, "alto_mm": 420, "modo": None,
                            "etiqueta": "A3 (29.7 x 42 cm) - Escaparate / Interior"},
    "cartel_a2":           {"tipo": "cartel", "ancho_mm": 420, "alto_mm": 594, "modo": None,
                            "etiqueta": "A2 (42 x 59.4 cm) - Eventos / Mediano"},
    "cartel_a1":           {"tipo": "cartel", "ancho_mm": 594, "alto_mm": 841, "modo": None,
                            "etiqueta": "A1 (59.4 x 84.1 cm) - Gran formato"},
    "cartel_50x70":        {"tipo": "cartel", "ancho_mm": 500, "alto_mm": 700, "modo": None,
                            "etiqueta": "50 x 70 cm - Mupi / Marquesina exterior"},
    "cartel_70x100":       {"tipo": "cartel", "ancho_mm": 700, "alto_mm": 1000, "modo": None,
                            "etiqueta": "70 x 100 cm - Mupi / Marquesina exterior"},
    "personalizado":       {"tipo": "cartel", "ancho_mm": 210, "alto_mm": 297, "modo": None,
                            "etiqueta": "Dimensiones personalizadas"},
}

TIPOS = ("cartel", "folleto")
ORIENTACIONES = ("vertical", "horizontal")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _dir_carteles() -> str:
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "documentos", "proyectos", "carteles")
    os.makedirs(base, exist_ok=True)
    return base


def _dir_miniaturas() -> str:
    base = os.path.join(_dir_carteles(), "miniaturas")
    os.makedirs(base, exist_ok=True)
    return base


def dimensiones_formato(formato: str, orientacion: str = "vertical"):
    """Devuelve (tipo, ancho_mm, alto_mm, modo) para `formato`, ya intercambiados si
    `orientacion == 'horizontal'`. `formato` desconocido -> trata como personalizado A4."""
    f = FORMATOS.get(formato) or FORMATOS["personalizado"]
    ancho, alto = f["ancho_mm"], f["alto_mm"]
    if orientacion == "horizontal":
        ancho, alto = alto, ancho
    return f["tipo"], ancho, alto, f["modo"]


def _doc_vacio(ancho_mm, alto_mm, modo=None) -> dict:
    return {"ancho_mm": float(ancho_mm), "alto_mm": float(alto_mm), "modo": modo,
           "fondo_color": "#FFFFFF", "elementos": []}


def _fila_a_cartel(fila: dict) -> dict:
    fila = dict(fila)
    try:
        fila["contenido"] = json.loads(fila.get("contenido_json") or "{}")
    except Exception:
        fila["contenido"] = {}
    if not fila["contenido"]:
        fila["contenido"] = _doc_vacio(fila.get("ancho_mm") or 210, fila.get("alto_mm") or 297,
                                       fila.get("modo"))
    fila.pop("contenido_json", None)
    return fila


# ── CRUD ───────────────────────────────────────────────────────────────────────────────────
def crear_cartel(titulo, *, id_proyecto=None, formato="personalizado", orientacion="vertical",
                 ancho_mm=None, alto_mm=None, dpi=300, id_empresa=None) -> int | None:
    """Crea un cartel/folleto nuevo con el lienzo vacío del tamaño del `formato` elegido (o las
    dimensiones personalizadas dadas). Devuelve el id o None si falla.

    `id_proyecto` es OPCIONAL (None = diseño independiente, el caso normal desde la GUI):
    Carteles/Folletos es una rama funcional aparte del tablero Kanban, no una característica de
    cada proyecto — no hace falta crear ni seleccionar ningún proyecto para diseñar un cartel."""
    titulo = (titulo or "Sin título").strip() or "Sin título"
    if orientacion not in ORIENTACIONES:
        orientacion = "vertical"
    tipo, ancho_cat, alto_cat, modo = dimensiones_formato(formato, orientacion)
    ancho = float(ancho_mm) if ancho_mm else ancho_cat
    alto = float(alto_mm) if alto_mm else alto_cat
    doc = _doc_vacio(ancho, alto, modo)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO proyecto_carteles (id_empresa, id_proyecto, titulo, tipo, formato, modo, "
                "ancho_mm, alto_mm, orientacion, dpi, contenido_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (_emp(id_empresa), id_proyecto, titulo, tipo, formato, modo, ancho, alto,
                 orientacion, int(dpi or 300), json.dumps(doc)))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_cartel: %s", e)
        return None


def listar_carteles(id_empresa=None, *, id_proyecto="__todos__", texto=None, tipo=None) -> list:
    """Lista los carteles de la empresa, más recientes primero. `id_proyecto` NO se filtra por
    defecto (todos los diseños, tengan o no proyecto asociado) — pásalo explícitamente (incluido
    `None`, para solo los independientes) si hace falta acotar por proyecto. `texto` filtra por
    título (LIKE); `tipo` filtra por 'cartel'/'folleto'."""
    filtros, params = ["id_empresa=%s"], [_emp(id_empresa)]
    if id_proyecto != "__todos__":
        if id_proyecto is None:
            filtros.append("id_proyecto IS NULL")
        else:
            filtros.append("id_proyecto=%s"); params.append(id_proyecto)
    if texto:
        filtros.append("titulo LIKE %s"); params.append(f"%{texto}%")
    if tipo in TIPOS:
        filtros.append("tipo=%s"); params.append(tipo)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proyecto_carteles WHERE " + " AND ".join(filtros) +
                        " ORDER BY modificado DESC", params)
            return [_fila_a_cartel(f) for f in _filas_a_dicts(cur, cur.fetchall())]
    except Exception as e:
        logger.error("listar_carteles: %s", e)
        return []


def obtener_cartel(id_cartel, id_empresa=None) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proyecto_carteles WHERE id=%s AND id_empresa=%s",
                        (id_cartel, _emp(id_empresa)))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return _fila_a_cartel(filas[0]) if filas else None
    except Exception as e:
        logger.error("obtener_cartel: %s", e)
        return None


def actualizar_cartel(id_cartel, id_empresa=None, *, titulo=None, contenido=None,
                      thumbnail_path=None, ancho_mm=None, alto_mm=None, dpi=None) -> bool:
    """Actualiza campos sueltos del cartel. `contenido` (dict, el modelo completo del lienzo) se
    serializa aquí; nunca se construye el UPDATE con campos vacíos (no-op seguro)."""
    sets, params = [], []
    if titulo is not None:
        sets.append("titulo=%s"); params.append(titulo.strip() or "Sin título")
    if contenido is not None:
        sets.append("contenido_json=%s"); params.append(json.dumps(contenido))
    if thumbnail_path is not None:
        sets.append("thumbnail_path=%s"); params.append(thumbnail_path)
    if ancho_mm is not None:
        sets.append("ancho_mm=%s"); params.append(float(ancho_mm))
    if alto_mm is not None:
        sets.append("alto_mm=%s"); params.append(float(alto_mm))
    if dpi is not None:
        sets.append("dpi=%s"); params.append(int(dpi))
    if not sets:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE proyecto_carteles SET {', '.join(sets)} WHERE id=%s AND id_empresa=%s",
                        (*params, id_cartel, _emp(id_empresa)))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("actualizar_cartel: %s", e)
        return False


def duplicar_cartel(id_cartel, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    c = obtener_cartel(id_cartel, id_empresa=eid)
    if not c:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO proyecto_carteles (id_empresa, id_proyecto, titulo, tipo, formato, modo, "
                "ancho_mm, alto_mm, orientacion, dpi, contenido_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (eid, c["id_proyecto"], f"{c['titulo']} (copia)", c["tipo"], c["formato"], c["modo"],
                 c["ancho_mm"], c["alto_mm"], c["orientacion"], c["dpi"], json.dumps(c["contenido"])))
            return cur.lastrowid
    except Exception as e:
        logger.error("duplicar_cartel: %s", e)
        return None


def eliminar_cartel(id_cartel, id_empresa=None) -> bool:
    eid = _emp(id_empresa)
    c = obtener_cartel(id_cartel, id_empresa=eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proyecto_carteles WHERE id=%s AND id_empresa=%s", (id_cartel, eid))
            ok = cur.rowcount > 0
    except Exception as e:
        logger.error("eliminar_cartel: %s", e)
        return False
    if ok and c and c.get("thumbnail_path") and os.path.exists(c["thumbnail_path"]):
        try:
            os.remove(c["thumbnail_path"])
        except OSError:
            pass
    return ok


# ── Miniatura / exportación (headless, delega en render_cartel) ──────────────────────────────
def generar_miniatura(id_cartel, id_empresa=None) -> str | None:
    """Renderiza el cartel a PNG pequeño (para la tarjeta de la galería) y lo guarda en
    `documentos/proyectos/carteles/miniaturas/`. Devuelve la ruta o None si falla."""
    eid = _emp(id_empresa)
    c = obtener_cartel(id_cartel, id_empresa=eid)
    if not c:
        return None
    from src.services.proyectos import render_cartel
    try:
        png = render_cartel.render_png(c["contenido"], dpi=72)
        ruta = os.path.join(_dir_miniaturas(), f"{id_cartel}.png")
        with open(ruta, "wb") as f:
            f.write(png)
        actualizar_cartel(id_cartel, id_empresa=eid, thumbnail_path=ruta)
        return ruta
    except Exception as e:
        logger.error("generar_miniatura(%s): %s", id_cartel, e)
        return None


def exportar_pdf(id_cartel, ruta_destino=None, *, sangrado_mm=3, marcas_corte=True,
                 id_empresa=None) -> tuple[bool, str]:
    """Exporta a PDF listo para imprenta. Devuelve (ok, ruta_o_motivo)."""
    eid = _emp(id_empresa)
    c = obtener_cartel(id_cartel, id_empresa=eid)
    if not c:
        return False, "cartel_no_encontrado"
    ruta = ruta_destino or os.path.join(_dir_carteles(), f"{c['titulo']}_{id_cartel}.pdf")
    from src.services.proyectos import render_cartel
    ok = render_cartel.render_pdf(c["contenido"], ruta, sangrado_mm=sangrado_mm,
                                  marcas_corte=marcas_corte)
    return (True, ruta) if ok else (False, "error_al_generar_pdf")


def exportar_imagen(id_cartel, ruta_destino=None, *, formato="PNG", dpi=150,
                    id_empresa=None) -> tuple[bool, str]:
    """Exportación rápida a PNG/JPG para revisión digital. Devuelve (ok, ruta_o_motivo)."""
    eid = _emp(id_empresa)
    c = obtener_cartel(id_cartel, id_empresa=eid)
    if not c:
        return False, "cartel_no_encontrado"
    from src.services.proyectos import render_cartel
    try:
        png = render_cartel.render_png(c["contenido"], dpi=dpi)
        ext = "jpg" if formato.upper() in ("JPG", "JPEG") else "png"
        ruta = ruta_destino or os.path.join(_dir_carteles(), f"{c['titulo']}_{id_cartel}.{ext}")
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        if ext == "jpg":
            from PIL import Image
            Image.open(__import__("io").BytesIO(png)).convert("RGB").save(ruta, format="JPEG", quality=92)
        else:
            with open(ruta, "wb") as f:
                f.write(png)
        return True, ruta
    except Exception as e:
        logger.error("exportar_imagen(%s): %s", id_cartel, e)
        return False, "error_al_exportar_imagen"


# ── Borrador asistido por IA (Asistente SOMA) ─────────────────────────────────────────────────
def generar_copy_ia(descripcion: str, *, tipo: str = "cartel", usuario: dict | None = None,
                    id_empresa) -> dict:
    """Genera un borrador de copy publicitario (título/subtítulo/cuerpo/CTA) a partir de una
    breve descripción del usuario, vía el MISMO cliente Anthropic degradable de SOMA. Devuelve
    SIEMPRE un dict, nunca lanza: éxito -> {"ok": True, "titulo","subtitulo","cuerpo","cta"};
    degradación -> {"ok": False, "motivo": "sin_api_key"|"sin_contexto"|"limite_ia"|
    "respuesta_invalida"|"error_inesperado"}."""
    from src.services.copilot.motor_llm import _MODELO, _cliente
    from src.services.ia_control_uso import LimiteUsoIAExcedido, ejecutar_tarea_ia

    cliente = _cliente()
    if cliente is None:
        return {"ok": False, "motivo": "sin_api_key"}
    if not id_empresa or not (descripcion or "").strip():
        return {"ok": False, "motivo": "sin_contexto"}

    prompt = (
        "Eres un diseñador publicitario experto. A partir de esta descripción breve de un "
        f"{'folleto' if tipo == 'folleto' else 'cartel'} publicitario, redacta un borrador de "
        "copy persuasivo y una llamada a la acción (CTA) clara.\n\n"
        f"Descripción: \"{descripcion.strip()}\"\n\n"
        "Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional ni bloques de código, "
        "con EXACTAMENTE estas claves: "
        '{"titulo": "título impactante, máx 60 caracteres", '
        '"subtitulo": "subtítulo de apoyo, máx 100 caracteres", '
        '"cuerpo": "cuerpo breve con la oferta/beneficio, máx 220 caracteres", '
        '"cta": "llamada a la acción corta, máx 30 caracteres"}'
    )
    id_usuario = (usuario or {}).get("id")
    try:
        respuesta = ejecutar_tarea_ia(
            id_empresa, id_usuario, "proyectos_carteles_ia",
            lambda: cliente.messages.create(
                model=_MODELO, max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            ))
    except LimiteUsoIAExcedido:
        return {"ok": False, "motivo": "limite_ia"}
    except Exception as e:
        logger.warning("generar_copy_ia: %s", e)
        return {"ok": False, "motivo": "error_inesperado"}

    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()
    # Degradación tolerante: si el modelo envuelve el JSON en un bloque ```json ... ``` (ocurre a
    # veces pese a la instrucción), se extrae el primer objeto { ... } en vez de fallar en seco.
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin == -1 or fin < inicio:
        return {"ok": False, "motivo": "respuesta_invalida"}
    try:
        datos = json.loads(texto[inicio:fin + 1])
    except Exception:
        return {"ok": False, "motivo": "respuesta_invalida"}
    if not isinstance(datos, dict) or not datos.get("titulo"):
        return {"ok": False, "motivo": "respuesta_invalida"}
    return {"ok": True, "titulo": str(datos.get("titulo") or "")[:60],
           "subtitulo": str(datos.get("subtitulo") or "")[:100],
           "cuerpo": str(datos.get("cuerpo") or "")[:220],
           "cta": str(datos.get("cta") or "")[:30]}


def construir_layout_desde_copy(copy: dict, ancho_mm: float, alto_mm: float) -> dict:
    """Distribuye el copy generado por IA en un lienzo del tamaño dado con una jerarquía visual
    sencilla y razonable (título grande arriba, subtítulo debajo, cuerpo en el centro, CTA como
    franja destacada abajo) — el PRIMER borrador que el usuario puede luego reordenar a mano en
    el editor, nunca el resultado final impuesto."""
    margen = max(10.0, ancho_mm * 0.06)
    ancho_util = ancho_mm - 2 * margen
    elementos = []
    if copy.get("titulo"):
        elementos.append({"tipo": "texto", "x": margen, "y": alto_mm * 0.08, "w": ancho_util,
                          "h": alto_mm * 0.16, "texto": copy["titulo"], "fuente": "negrita",
                          "tamano_pt": max(22, ancho_mm * 0.09), "color": "#111111",
                          "alineacion": "centro", "interlineado": 1.15, "z": 0})
    if copy.get("subtitulo"):
        elementos.append({"tipo": "texto", "x": margen, "y": alto_mm * 0.26, "w": ancho_util,
                          "h": alto_mm * 0.10, "texto": copy["subtitulo"], "fuente": "regular",
                          "tamano_pt": max(14, ancho_mm * 0.05), "color": "#333333",
                          "alineacion": "centro", "interlineado": 1.2, "z": 1})
    if copy.get("cuerpo"):
        elementos.append({"tipo": "texto", "x": margen, "y": alto_mm * 0.42, "w": ancho_util,
                          "h": alto_mm * 0.30, "texto": copy["cuerpo"], "fuente": "regular",
                          "tamano_pt": max(11, ancho_mm * 0.035), "color": "#1A1A1A",
                          "alineacion": "izquierda", "interlineado": 1.3, "z": 2})
    if copy.get("cta"):
        franja_h = alto_mm * 0.09
        elementos.append({"tipo": "forma", "forma": "rectangulo", "x": margen,
                          "y": alto_mm - franja_h - margen, "w": ancho_util, "h": franja_h,
                          "color": "#00FFC6", "relleno": True, "grosor_mm": 0, "z": 3})
        elementos.append({"tipo": "texto", "x": margen, "y": alto_mm - franja_h - margen + franja_h * 0.2,
                          "w": ancho_util, "h": franja_h * 0.6, "texto": copy["cta"], "fuente": "negrita",
                          "tamano_pt": max(14, ancho_mm * 0.045), "color": "#0E1117",
                          "alineacion": "centro", "interlineado": 1.0, "z": 4})
    return {"ancho_mm": float(ancho_mm), "alto_mm": float(alto_mm), "modo": None,
           "fondo_color": "#FFFFFF", "elementos": elementos}
