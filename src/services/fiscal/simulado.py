"""
Proveedor fiscal SIMULADO (C3.1) — base funcional para pruebas, SIN lógica legal.

Construye y persiste un registro fiscal real (numeración + ENCADENADO HASH vía
`src.db.fiscal`) y genera un QR de marcador de posición. No firma ni envía nada.
Sirve para validar la arquitectura del núcleo antes de implementar Verifactu/
Facturae (C3.3/C3.4). Cubre todos los territorios para no bloquear pruebas.
"""

import logging

from src.db import fiscal as fiscal_db
from src.services.fiscal.base import ProveedorFiscal, RegistroFiscal
from src.services.fiscal.registry import registrar_proveedor

logger = logging.getLogger("fiscal.simulado")


@registrar_proveedor("simulado", territorios=("comun", "araba", "bizkaia", "gipuzkoa"))
class ProveedorSimulado(ProveedorFiscal):
    nombre = "simulado"

    def _qr(self, datos: dict) -> str:
        # Marcador (no es el QR legal de Verifactu/TBAI; eso llega en C3.3/C3.4).
        return "SIMULADO|" + "|".join(f"{k}={datos.get(k)}" for k in ("serie", "numero", "total"))

    def registrar(self, tipo, referencia=None, total=0.0, payload=None) -> RegistroFiscal:
        reg = fiscal_db.insertar_registro(
            tipo=tipo, referencia=referencia, total=total, payload=payload,
            proveedor=self.nombre, estado="generado")
        if not reg:
            return RegistroFiscal(tipo=tipo, referencia=referencia, total=total,
                                  proveedor=self.nombre, estado="error")
        qr = self._qr(reg)
        fiscal_db.actualizar_estado(reg["id"], "generado")
        # Persistimos el QR de marcador en el propio registro.
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE fiscal_registros SET qr=%s WHERE id=%s", (qr, reg["id"]))
                conn.commit()
        except Exception as e:
            logger.debug("No se pudo guardar el QR simulado: %s", e)
        reg["qr"] = qr
        return RegistroFiscal.desde_fila(reg)

    def anular(self, registro: RegistroFiscal) -> RegistroFiscal:
        reg = fiscal_db.insertar_registro(
            tipo="anulacion", referencia=str(registro.referencia or registro.id),
            total=-(registro.total or 0), proveedor=self.nombre, estado="generado")
        return RegistroFiscal.desde_fila(reg) if reg else registro
