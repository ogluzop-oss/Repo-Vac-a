"""
Reetiquetado automático (petición explícita, Alta artículo del Portal Empresa): "el ERP debe
conectar con una impresora de etiquetas configurada e imprimir automáticamente nuevas etiquetas
(ref. interna + PVP + sección)". Reutiliza TAL CUAL el motor de etiquetas ya existente
(`services.etiquetas.pdf.GeneradorEtiquetas`, extendido con `seccion`) — este módulo solo añade
la configuración de la impresora y el envío a imprimir, sin tocar la generación del PDF.

Honestidad (mismo criterio que el resto del ERP, p. ej. Cámaras/Fiscal): no existe ningún driver
de impresora "simulado" — se usa el mecanismo REAL que ya ofrece Windows para imprimir un PDF (el
verbo de shell "print" sobre el visor de PDF predeterminado, que a su vez imprime en la impresora
predeterminada del sistema — el mismo camino que un doble clic + "Imprimir" desde el Explorador).
Si no hay impresora predeterminada, no hay visor de PDF registrado, o el sistema no es Windows,
se degrada limpiamente: el PDF queda generado y registrado en el Centro Documental igualmente,
pero `impresa=False` — NUNCA se informa una impresión que no ha ocurrido.

Configuración: el nombre de la impresora es un dato de MÁQUINA (qué impresora física hay
conectada a ESTE PC), no de empresa — se guarda en `documentos/app_settings.json` (mismo fichero
y patrón que ya usa `src/utils/i18n.py` para el idioma), bajo la clave "impresora_etiquetas".
Si no se configura ninguna, se usa la impresora predeterminada del sistema.
"""

import json
import logging
import os
import platform

logger = logging.getLogger("etiquetas.impresion")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_SETTINGS_PATH = os.path.join(_PROJECT_ROOT, "documentos", "app_settings.json")


def _leer_settings() -> dict:
    try:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception as e:
        logger.debug("_leer_settings: %s", e)
    return {}


def obtener_impresora_configurada() -> str | None:
    """Nombre de la impresora de etiquetas configurada en ESTA máquina, o None si se usa la
    predeterminada del sistema."""
    return (_leer_settings().get("impresora_etiquetas") or "").strip() or None


def configurar_impresora_etiquetas(nombre_impresora: str | None) -> bool:
    """Guarda (o limpia, si `nombre_impresora` es vacío/None) la impresora de etiquetas de esta
    máquina. No valida que la impresora exista — eso lo decide el propio sistema operativo al
    intentar imprimir (degradación honesta, nunca se simula una validación que no se puede hacer
    sin acceso real al spooler)."""
    try:
        data = _leer_settings()
        if nombre_impresora and nombre_impresora.strip():
            data["impresora_etiquetas"] = nombre_impresora.strip()
        else:
            data.pop("impresora_etiquetas", None)
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("configurar_impresora_etiquetas: %s", e)
        return False


def _enviar_a_imprimir(ruta_pdf: str) -> bool:
    """Intenta enviar `ruta_pdf` a imprimir. Si hay una impresora de etiquetas CONFIGURADA
    (`obtener_impresora_configurada`), usa el verbo de shell real de Windows "printto" (el mismo
    que usa el Explorador en "Imprimir en" del menú contextual) para dirigirlo a esa impresora
    concreta — vía `ShellExecuteW` de la librería estándar (`ctypes`), sin depender de pywin32.
    Si no hay ninguna configurada, o el "printto" falla, cae al verbo "print" de toda la vida sobre
    el visor de PDF predeterminado (impresora predeterminada del sistema). `True` solo si el
    sistema operativo aceptó la orden — nunca se asume éxito sin que el SO lo confirme."""
    if platform.system() != "Windows":
        logger.info("Auto-impresión de etiqueta no disponible (SO no Windows); PDF generado en %s",
                   ruta_pdf)
        return False
    impresora = obtener_impresora_configurada()
    if impresora:
        try:
            import ctypes
            # ShellExecuteW devuelve un HINSTANCE: un valor > 32 indica éxito (misma convención
            # que documenta la API de Windows para esta llamada).
            resultado = ctypes.windll.shell32.ShellExecuteW(
                None, "printto", ruta_pdf, f'"{impresora}"', None, 0)
            if resultado > 32:
                return True
            logger.warning("No se pudo imprimir en la impresora configurada %r (código %s); "
                           "se prueba con la predeterminada.", impresora, resultado)
        except Exception as e:
            logger.warning("Fallo al imprimir en la impresora configurada %r: %s", impresora, e)
    try:
        os.startfile(ruta_pdf, "print")  # noqa: S606 — verbo de shell real de Windows, no un exec
        return True
    except Exception as e:
        logger.warning("No se pudo enviar la etiqueta a imprimir (%s): %s", ruta_pdf, e)
        return False


def generar_e_imprimir_etiqueta(codigo, nombre, precio, *, seccion=None, formato="70x35",
                                tipo="normal", id_empresa=None, id_tienda=None, usuario=None) -> dict:
    """Genera la etiqueta (ref. interna + PVP + sección) con el motor YA EXISTENTE y la envía a la
    impresora configurada (o la predeterminada del sistema). Siempre registra el PDF en el Centro
    Documental, incluso si la impresión automática no está disponible — el usuario nunca se queda
    sin el PDF por un fallo del paso de impresión."""
    try:
        from src.services.etiquetas.pdf import GeneradorEtiquetas
        ruta = GeneradorEtiquetas.generar(codigo, nombre, precio, formato=formato, tipo=tipo,
                                          seccion=seccion)
    except Exception as e:
        logger.error("generar_e_imprimir_etiqueta: fallo al generar el PDF (%s): %s", codigo, e)
        return {"ok": False, "error": "no_se_pudo_generar"}

    id_documento = None
    try:
        from src.db.documentos import registrar_documento
        id_documento = registrar_documento(ruta, tipo="etiqueta", nombre=os.path.basename(ruta),
                                           referencia=str(codigo), id_empresa=id_empresa,
                                           id_tienda=id_tienda, id_usuario=usuario)
    except Exception as e:
        logger.debug("generar_e_imprimir_etiqueta: no se pudo registrar el documento (%s): %s", codigo, e)

    impresa = _enviar_a_imprimir(ruta)
    return {"ok": True, "ruta": ruta, "id_documento": id_documento, "impresa": impresa}
