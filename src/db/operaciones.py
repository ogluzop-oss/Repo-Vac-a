import logging

logger = logging.getLogger(__name__)


# ============================================================
# BLOQUE REGISTRO DE TRASPASOS
# ============================================================

def guardar_traspaso_db(datos: dict):
    """
    Registra un traspaso logístico delegando en la capa logística unificada.
    Acepta el dict legacy con claves: tienda_origen, tienda_destino, usuario,
    observaciones, fecha_entrega, items (lista de {codigo, nombre, cantidad, pale}).
    """
    try:
        from src.db.logistica import guardar_traspaso_logistico

        origen       = datos.get("tienda_origen", "DESCONOCIDO")
        destino      = datos.get("tienda_destino", "DESCONOCIDO")
        usuario      = datos.get("usuario", "SISTEMA")
        observaciones = datos.get("observaciones", "")
        fecha_envio  = datos.get("fecha_entrega")

        # Agrupa los items por palé
        pales: dict = {}
        for item in datos.get("items", []):
            pale_id = str(item.get("pale") or "PALE1").upper().replace(" ", "")
            pale = pales.setdefault(
                pale_id,
                {"id_visual": pale_id, "peso": None, "articulos": []},
            )
            pale["articulos"].append(
                {
                    "codigo":   str(item.get("codigo", "")),
                    "nombre":   str(item.get("nombre", item.get("codigo", ""))),
                    "cantidad": int(item.get("cantidad", 0)),
                }
            )

        resultado = guardar_traspaso_logistico(
            origen=origen,
            destino=destino,
            usuario=usuario,
            observaciones=observaciones,
            pales=pales,
            fecha_envio=fecha_envio,
        )

        if resultado:
            id_doc = resultado.get("id_documento", "")
            logger.info(f"Traspaso {id_doc} registrado correctamente.")
            return True, id_doc

        return False, "Error en guardar_traspaso_logistico"

    except Exception as e:
        logger.error(f"Error al procesar traspaso en DB: {e}")
        return False, str(e)
