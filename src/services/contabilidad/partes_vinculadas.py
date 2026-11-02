"""
Operaciones con Partes Vinculadas (Memoria/Cuentas Anuales). Registro de DIVULGACIÓN manual:
quién cuenta como "parte vinculada" (administrador, socio significativo, familiar cercano, u otra
empresa del grupo) es una decisión legal/societaria que declara un administrador — no se infiere
de ninguna tabla operativa existente (facturas, nóminas, compras...), así que esto NUNCA rellena
el registro automáticamente a partir de otros datos: es alta manual, 100% explícita.

Tabla `contab_partes_vinculadas` (migración 0278). Sin motor paralelo: esto es un libro de
divulgación para la Memoria, no un módulo contable (no genera asientos, no afecta balances).
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("contab.partes_vinculadas")

# Vocabulario cerrado de relación — el que pide la nota de Memoria del PGC-PYMES.
RELACIONES = ("administrador", "socio", "familiar", "empresa_grupo", "otra")


def _empresa(id_empresa=None):
    try:
        from src.services.contabilidad.identidad_contabilidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID


def registrar_parte_vinculada(anio, nombre, relacion, importe, *, descripcion=None, fecha=None,
                               creado_por=None, id_empresa=None) -> int | None:
    """Alta manual de una operación con parte vinculada del ejercicio `anio`. `relacion` debe ser
    uno de `RELACIONES`. Nunca se llama automáticamente: solo desde una acción explícita del
    administrador (GUI/wizard de Memoria, en el paso posterior de wiring)."""
    id_empresa = _empresa(id_empresa)
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("nombre obligatorio")
    if relacion not in RELACIONES:
        raise ValueError(f"relacion invalida: {relacion!r} (valores válidos: {RELACIONES})")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO contab_partes_vinculadas "
                "(id_empresa, anio, nombre, relacion, descripcion, importe, fecha, creado_por) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, int(anio), nombre[:255], relacion, descripcion,
                 round(float(importe or 0), 2), fecha, creado_por))
            nuevo_id = cur.lastrowid
            conn.commit()
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("contabilidad", "PARTE_VINCULADA_ALTA", "contab_partes_vinculadas",
                          f"id={nuevo_id} anio={anio} {nombre} ({relacion}) {importe}€")
        except Exception:
            pass
        return nuevo_id
    except ValueError:
        raise
    except Exception as e:
        logger.error("registrar_parte_vinculada: %s", e)
        return None


def listar_partes_vinculadas(anio, id_empresa=None) -> list:
    """Operaciones registradas del ejercicio `anio`. Lista vacía = honestamente sin registros
    (la Memoria debe mostrar la declaración negativa, nunca fabricar una fila)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM contab_partes_vinculadas WHERE id_empresa=%s AND anio=%s "
                "ORDER BY fecha, id", (id_empresa, int(anio)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_partes_vinculadas(%s): %s", anio, e)
        return []


def eliminar_parte_vinculada(id_registro, *, id_empresa=None) -> bool:
    """Borra una fila mal registrada (corrección manual). Baja física: este registro no es un
    asiento contable ni tiene efectos aguas abajo, así que no necesita baja lógica."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM contab_partes_vinculadas WHERE id=%s AND id_empresa<=>%s",
                       (id_registro, id_empresa))
            borrado = cur.rowcount > 0
            conn.commit()
        if borrado:
            try:
                from src.db.conexion import log_auditoria
                log_auditoria("contabilidad", "PARTE_VINCULADA_BAJA", "contab_partes_vinculadas",
                              f"id={id_registro}")
            except Exception:
                pass
        return borrado
    except Exception as e:
        logger.error("eliminar_parte_vinculada(%s): %s", id_registro, e)
        return False
