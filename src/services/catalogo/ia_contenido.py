"""
Asistente IA de contenido para la ficha de producto del Catálogo (Fase 1 — maduración del PIM,
NO un motor de IA nuevo en paralelo): genera descripción/meta-título/meta-descripción con un
tono elegible, reutilizando AL 100% la infraestructura de IA ya existente:

- Mismo cliente Anthropic degradable y el mismo modelo que SOMA
  (`src.services.copilot.motor_llm._cliente`/`_MODELO`) — nunca se crea un segundo cliente/motor.
- Mismo punto ÚNICO de ejecución medida/auditada (`src.services.ia_control_uso.ejecutar_tarea_ia`),
  el mismo que ya usa `motor_llm._llamar_claude` — cuenta para la misma cuota/coste por empresa.

A diferencia de `motor_llm.responder_con_llm` (turno conversacional de SOMA: historial
persistente + herramientas MCP + confirmaciones), esto es una llamada de UN SOLO TURNO, sin
herramientas ni historial — "genera un texto para este campo" no es una conversación, así que no
tiene sentido hacerla pasar por el motor conversacional completo.

Nunca inventa texto: si el cliente no está disponible o se agota la cuota, degrada con un motivo
honesto (`{"ok": False, "motivo": ...}`) — igual que el resto de integraciones IA de la app
(`services.ia.documental.resumen_texto`, `motor_llm.responder_con_llm`).
"""

import logging

from src.services.copilot.motor_llm import _MODELO, _cliente
from src.services.ia_control_uso import LimiteUsoIAExcedido, ejecutar_tarea_ia

logger = logging.getLogger("catalogo.ia_contenido")

_TONOS = {
    "comercial": "cercano, persuasivo y orientado a vender",
    "elegante": "sofisticado, cuidado, propio de una marca premium",
    "tecnico": "preciso, detallado, centrado en especificaciones objetivas",
}

# (descripción del encargo al modelo, límite de caracteres sugerido — Shopify/SEO estándar)
_CAMPOS = {
    "descripcion": ("una descripción de producto para una ficha de tienda online", 600),
    "seo_title": ("un meta-título SEO (muy breve, impactante)", 60),
    "seo_descripcion": ("una meta-descripción SEO para resultados de búsqueda", 155),
}

CAMPOS_VALIDOS = tuple(_CAMPOS.keys())
TONOS_VALIDOS = tuple(_TONOS.keys())


def generar_texto(campo: str, nombre_producto: str, atributos: dict | None = None,
                  tono: str = "comercial", *, usuario: dict | None, id_empresa) -> dict:
    """Genera texto para `campo` (uno de `CAMPOS_VALIDOS`). Devuelve SIEMPRE un dict, nunca lanza:
    éxito → `{"ok": True, "texto": str}`; degradación → `{"ok": False, "motivo": str}` (motivos:
    "campo_invalido"/"sin_api_key"/"sin_contexto"/"limite_ia"/"respuesta_vacia"/"error_inesperado")."""
    if campo not in _CAMPOS:
        return {"ok": False, "motivo": "campo_invalido"}
    cliente = _cliente()
    if cliente is None:
        return {"ok": False, "motivo": "sin_api_key"}
    if not id_empresa or not (nombre_producto or "").strip():
        return {"ok": False, "motivo": "sin_contexto"}

    descripcion_campo, limite = _CAMPOS[campo]
    estilo = _TONOS.get(tono, _TONOS["comercial"])
    atributos_txt = ", ".join(f"{k}: {v}" for k, v in (atributos or {}).items() if v)
    prompt = (
        f"Escribe {descripcion_campo} para el producto \"{nombre_producto.strip()}\""
        + (f" (atributos: {atributos_txt})" if atributos_txt else "")
        + f". Tono {estilo}. Máximo {limite} caracteres. "
        "Responde ÚNICAMENTE con el texto final, sin comillas, sin explicaciones ni prefijos."
    )
    id_usuario = (usuario or {}).get("id")
    try:
        respuesta = ejecutar_tarea_ia(
            id_empresa, id_usuario, "catalogo_ia_contenido",
            lambda: cliente.messages.create(
                model=_MODELO, max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            ))
    except LimiteUsoIAExcedido:
        return {"ok": False, "motivo": "limite_ia"}
    except Exception as e:
        logger.warning("generar_texto(%s): %s", campo, e)
        return {"ok": False, "motivo": "error_inesperado"}

    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()
    texto = texto.strip('"').strip()
    if not texto:
        return {"ok": False, "motivo": "respuesta_vacia"}
    return {"ok": True, "texto": texto[:limite]}


# (tipo_bloque, campo) → (descripción del encargo, límite de caracteres sugerido) — Fase 4
# (editor visual del storefront, `gui/tema_editor_dialog.py`): MISMO motor/chokepoint que
# `generar_texto` de arriba (no un segundo cliente IA), solo cambia el catálogo de campos porque
# aquí el texto es de marca/marketing de la TIENDA, no de un producto concreto.
_CAMPOS_BLOQUE = {
    ("hero", "titulo"): ("un título principal (hero) para la portada de una tienda online", 70),
    ("hero", "subtitulo"): ("un subtítulo que acompañe al título principal de la portada", 140),
    ("hero", "texto_boton"): ("el texto de un botón de llamada a la acción (call to action)", 24),
    ("texto", "titulo"): ("un título breve para un bloque de texto de la tienda", 70),
    ("texto", "texto"): ("el cuerpo de un bloque de texto para la tienda (p. ej. sobre la marca)", 500),
    ("banner", "texto"): ("un texto corto superpuesto a un banner con imagen", 100),
}

CAMPOS_BLOQUE_VALIDOS = tuple(_CAMPOS_BLOQUE.keys())


def generar_texto_bloque(tipo_bloque: str, campo: str, nombre_tienda: str,
                        tono: str = "comercial", *, usuario: dict | None, id_empresa) -> dict:
    """Igual que `generar_texto`, pero para los bloques del editor visual de la tienda (título/
    subtítulo/texto de hero, bloque de texto, banner) en vez de los campos de un producto."""
    clave = (tipo_bloque, campo)
    if clave not in _CAMPOS_BLOQUE:
        return {"ok": False, "motivo": "campo_invalido"}
    cliente = _cliente()
    if cliente is None:
        return {"ok": False, "motivo": "sin_api_key"}
    if not id_empresa or not (nombre_tienda or "").strip():
        return {"ok": False, "motivo": "sin_contexto"}

    descripcion_campo, limite = _CAMPOS_BLOQUE[clave]
    estilo = _TONOS.get(tono, _TONOS["comercial"])
    prompt = (
        f"Escribe {descripcion_campo} para la tienda online \"{nombre_tienda.strip()}\". "
        f"Tono {estilo}. Máximo {limite} caracteres. "
        "Responde ÚNICAMENTE con el texto final, sin comillas, sin explicaciones ni prefijos."
    )
    id_usuario = (usuario or {}).get("id")
    try:
        respuesta = ejecutar_tarea_ia(
            id_empresa, id_usuario, "catalogo_ia_contenido",
            lambda: cliente.messages.create(
                model=_MODELO, max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            ))
    except LimiteUsoIAExcedido:
        return {"ok": False, "motivo": "limite_ia"}
    except Exception as e:
        logger.warning("generar_texto_bloque(%s, %s): %s", tipo_bloque, campo, e)
        return {"ok": False, "motivo": "error_inesperado"}

    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text").strip()
    texto = texto.strip('"').strip()
    if not texto:
        return {"ok": False, "motivo": "respuesta_vacia"}
    return {"ok": True, "texto": texto[:limite]}
