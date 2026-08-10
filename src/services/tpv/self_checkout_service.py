"""
Self-Checkout Service — Smart Manager AI TPV Enterprise
Business logic for unattended (self-service) checkout lanes:
  - restricted product detection (alcohol, tobacco → age verification)
  - expected-weight validation (anti-fraud bagging area check)
  - assistance requests routing
"""
from __future__ import annotations

import logging

logger = logging.getLogger("tpv.selfcheckout")

# Categories / sections that require an attendant's age authorization
CATEGORIAS_RESTRINGIDAS = {
    "ALCOHOL", "BEBIDAS ALCOHOLICAS", "BEBIDAS ALCOHÓLICAS",
    "TABACO", "CIGARRILLOS", "VINOS", "LICORES", "CERVEZA",
}

# Keywords in product name that flag restriction even if category is generic
PALABRAS_RESTRINGIDAS = {
    "VINO", "CERVEZA", "WHISKY", "RON", "VODKA", "GINEBRA", "LICOR",
    "TABACO", "CIGARR", "VERMUT", "CHAMPAN", "CHAMPÁN", "CAVA",
}


def _familia_restriccion(articulo: dict):
    """(flag_restringida, nombre_familia) del artículo, resuelto por su FAMILIA (fuente ÚNICA de
    categorización). El dict puede traerlo ya (`familia_restringida`/`familia_nombre`) o se resuelve por
    `id_familia`. Best-effort: nunca lanza."""
    if articulo.get("familia_restringida"):
        return True, (articulo.get("familia_nombre") or "")
    if articulo.get("familia_nombre"):
        return False, articulo.get("familia_nombre")
    idf = articulo.get("id_familia")
    if not idf:
        return False, ""
    try:
        from src.db import familias as _F
        fam = _F.obtener_familia(idf, articulo.get("id_empresa"))
        if fam:
            return bool(fam.get("restringida")), (fam.get("nombre") or "")
    except Exception as e:  # pragma: no cover
        logger.debug("resolver familia restringida: %s", e)
    return False, ""


def es_producto_restringido(articulo: dict) -> bool:
    """
    True if the product needs attendant authorization (age check).

    Categorización por FAMILIA (fuente única `familias_producto`): la familia marcada como `restringida`, o
    cuyo NOMBRE es una categoría restringida (alcohol/tabaco…). Los antiguos campos libres
    `articulos.seccion`/`categoria` ya NO se usan (evita información desfasada). El NOMBRE del producto se
    conserva como red de seguridad.
    """
    if not articulo:
        return False
    flag, fam_nombre = _familia_restriccion(articulo)
    if flag or (fam_nombre or "").upper() in CATEGORIAS_RESTRINGIDAS:
        return True
    nom = (articulo.get("nombre") or articulo.get("descripcion") or "").upper()
    return any(p in nom for p in PALABRAS_RESTRINGIDAS)


def validar_peso_esperado(peso_real: float, peso_esperado: float,
                          tolerancia: float = 0.05) -> tuple[bool, str]:
    """
    Anti-fraud bagging-area check.
    Returns (ok, message). tolerancia is the fraction allowed (5% default).
    If peso_esperado is 0 (unknown), validation is skipped.
    """
    if peso_esperado <= 0:
        return True, ""   # no reference weight → skip
    diff = abs(peso_real - peso_esperado)
    margen = peso_esperado * tolerancia
    if diff > margen:
        return False, (
            "El peso detectado no coincide con el esperado. "
            "Espere asistencia de personal."
        )
    return True, ""


def registrar_solicitud_ayuda(caja_id: str, motivo: str = "AYUDA GENERAL",
                              empleado: str = "AUTOCOBRO") -> bool:
    """
    Logs an assistance request to the audit table so a supervisor
    dashboard / notification can pick it up.
    """
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO auditoria_logs
                      (usuario, accion, tabla_afectada, detalles)
                    VALUES (%s, %s, %s, %s)
                """, (
                    empleado,
                    "SOLICITUD AYUDA AUTOCOBRO",
                    "tpv_autocobro",
                    f"caja={caja_id} motivo={motivo}",
                ))
            conn.commit()
        logger.info(f"Solicitud de ayuda registrada: caja={caja_id} motivo={motivo}")
        return True
    except Exception as e:
        logger.error(f"registrar_solicitud_ayuda: {e}")
        return False


def registrar_autorizacion_edad(caja_id: str, autorizado_por: str,
                                articulo: str) -> bool:
    """Audit trail when an attendant authorizes an age-restricted item."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO auditoria_logs
                      (usuario, accion, tabla_afectada, detalles)
                    VALUES (%s, %s, %s, %s)
                """, (
                    autorizado_por,
                    "AUTORIZACIÓN EDAD AUTOCOBRO",
                    "tpv_autocobro",
                    f"caja={caja_id} articulo={articulo}",
                ))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"registrar_autorizacion_edad: {e}")
        return False


# ============================================================
# DUAL-PLATFORM ANTI-FRAUD CONTROLLER
# ============================================================
# Models a modern self-checkout with two weighing platforms:
#   - LEFT  ("entrada"): cart of un-scanned items the customer picks from.
#   - RIGHT ("bagging"): scanned items must be placed here; its weight must
#     match the expected total of scanned products (anti-fraud).
#
# State machine per scan:
#   ESPERANDO_ESCANEO → (scan) → ESPERANDO_DEPOSITO → (weight matches) → OK
# Discrepancies (item not deposited / deposited without scanning / weight
# mismatch) raise a block that only "solicitar ayuda" + authorization clears.

ESTADO_LIBRE        = "libre"            # nothing pending
ESTADO_ESPERA_PESO  = "espera_deposito"  # scanned, waiting for item on bagging area
ESTADO_BLOQUEADO    = "bloqueado"        # discrepancy detected
ESTADO_OK           = "ok"

# Default per-item weight (kg) used when an article has no real weight on file.
PESO_POR_DEFECTO_KG = 0.300
TOLERANCIA_KG       = 0.060   # ±60 g accepted (covers light packaging variance)


class BaggingAreaController:
    """
    Tracks expected vs. measured weight on the bagging platform.
    Pure logic — no Qt. The UI feeds it scale readings and reacts to states.
    """

    def __init__(self, tolerancia_kg: float = TOLERANCIA_KG):
        self._tolerancia = tolerancia_kg   # suelo global de tolerancia (mínimo garantizado)
        self._peso_esperado = 0.0          # suma de pesos esperados de los artículos escaneados
        self._tolerancia_acum = 0.0        # suma de tolerancias por artículo de lo escaneado
        self._estado = ESTADO_LIBRE
        self._pendiente_kg = 0.0           # peso que el último escaneo debe aportar

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def peso_esperado(self) -> float:
        return round(self._peso_esperado, 3)

    @property
    def tolerancia_efectiva(self) -> float:
        """Tolerancia aplicada al total = SUMA de las tolerancias por artículo de lo escaneado. Con el
        carrito vacío, cae al suelo global. Una tolerancia por artículo más ESTRICTA se respeta (no la
        afloja el suelo global); un artículo sin dato aporta el suelo global como tolerancia por unidad."""
        return round(self._tolerancia_acum if self._tolerancia_acum > 0 else self._tolerancia, 3)

    @staticmethod
    def peso_articulo(articulo: dict) -> float:
        """Peso esperado por unidad (kg): `peso_unitario` de la ficha (Capa 1); si no, valor por defecto."""
        for k in ("peso_unitario", "peso", "peso_kg"):
            v = articulo.get(k) if articulo else None
            try:
                if v and float(v) > 0:
                    return float(v)
            except (TypeError, ValueError):
                pass
        return PESO_POR_DEFECTO_KG

    @staticmethod
    def tolerancia_articulo(articulo: dict) -> float:
        """Tolerancia por artículo (kg): `tolerancia_peso` de la ficha; si no, el suelo global por unidad
        (mantiene el comportamiento anterior para artículos sin dato de seguridad)."""
        v = articulo.get("tolerancia_peso") if articulo else None
        try:
            if v and float(v) > 0:
                return float(v)
        except (TypeError, ValueError):
            pass
        return TOLERANCIA_KG

    def al_escanear(self, articulo: dict):
        """Called right after a successful scan: expect the item on the scale."""
        self._pendiente_kg = self.peso_articulo(articulo)
        self._peso_esperado = round(self._peso_esperado + self._pendiente_kg, 3)
        self._tolerancia_acum = round(self._tolerancia_acum + self.tolerancia_articulo(articulo), 3)
        self._estado = ESTADO_ESPERA_PESO

    def al_eliminar(self, articulo: dict):
        """Called when an item is removed: expect weight to DROP."""
        w = self.peso_articulo(articulo)
        self._peso_esperado = round(max(0.0, self._peso_esperado - w), 3)
        self._tolerancia_acum = round(max(0.0, self._tolerancia_acum - self.tolerancia_articulo(articulo)), 3)
        self._pendiente_kg = -w
        self._estado = ESTADO_ESPERA_PESO

    def verificar(self, peso_medido: float) -> tuple[str, str]:
        """
        Compare measured weight against expected using the effective (per-article) tolerance.
        Returns (estado, mensaje). Sin hardware, la UI pasa peso_medido == esperado para aceptar.
        """
        tol = self.tolerancia_efectiva
        diff = abs(peso_medido - self._peso_esperado)
        if diff <= tol:
            self._estado = ESTADO_OK
            self._pendiente_kg = 0.0
            return ESTADO_OK, ""
        if peso_medido < self._peso_esperado - tol:
            self._estado = ESTADO_ESPERA_PESO
            return (ESTADO_ESPERA_PESO,
                    "Coloca el artículo en la zona de embolsado para continuar.")
        # heavier than expected → unscanned item placed
        self._estado = ESTADO_BLOQUEADO
        return (ESTADO_BLOQUEADO,
                "Se ha detectado un artículo sin escanear en la zona de embolsado.")

    def desbloquear(self):
        """Called after staff authorization to clear a block."""
        self._estado = ESTADO_OK
        self._pendiente_kg = 0.0

    def reset(self):
        self._peso_esperado = 0.0
        self._tolerancia_acum = 0.0
        self._pendiente_kg = 0.0
        self._estado = ESTADO_LIBRE
