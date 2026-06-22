"""
Conciliación bancaria — persistencia (rama Tesorería, FASE 8).

CRUD de extractos_bancarios, extracto_lineas y conciliaciones. La lógica de importación y
emparejamiento vive en src/services/tesoreria/conciliacion.py.
"""

import hashlib
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("conciliacion_db")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _filas(cur):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def hash_linea(id_extracto, fecha, importe, concepto, referencia) -> str:
    base = f"{id_extracto}|{fecha}|{importe}|{concepto}|{referencia}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def crear_extracto(id_cuenta, formato, *, nombre_fichero=None, fecha_inicio=None,
                   fecha_fin=None, saldo_inicial=None, saldo_final=None,
                   num_lineas=0, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO extractos_bancarios (id_empresa, id_cuenta, nombre_fichero, formato, "
                "fecha_inicio, fecha_fin, saldo_inicial, saldo_final, num_lineas) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cuenta, nombre_fichero, (formato or "CSV").upper(),
                 fecha_inicio, fecha_fin, saldo_inicial, saldo_final, num_lineas))
            eid = cur.lastrowid
            conn.commit()
            return eid
    except Exception as e:
        logger.error("crear_extracto: %s", e)
        return None


def anadir_linea(id_extracto, fecha, importe, *, concepto=None, referencia=None,
                 saldo=None, id_empresa=None) -> int | None:
    """Inserta una línea de extracto (idempotente por hash dentro del extracto)."""
    id_empresa = _emp(id_empresa)
    h = hash_linea(id_extracto, fecha, importe, concepto, referencia)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM extracto_lineas WHERE id_extracto=%s AND hash=%s LIMIT 1",
                        (id_extracto, h))
            ya = cur.fetchone()
            if ya:
                return ya[0] if not isinstance(ya, dict) else list(ya.values())[0]
            cur.execute(
                "INSERT INTO extracto_lineas (id_empresa, id_extracto, fecha, importe, concepto, "
                "referencia, saldo, hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_extracto, fecha, round(float(importe or 0), 2), concepto,
                 referencia, saldo, h))
            lid = cur.lastrowid
            conn.commit()
            return lid
    except Exception as e:
        logger.error("anadir_linea: %s", e)
        return None


def actualizar_num_lineas(id_extracto, id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM extracto_lineas WHERE id_extracto=%s", (id_extracto,))
            n = cur.fetchone()
            n = n[0] if not isinstance(n, dict) else list(n.values())[0]
            cur.execute("UPDATE extractos_bancarios SET num_lineas=%s WHERE id=%s AND id_empresa=%s",
                        (n, id_extracto, id_empresa))
            conn.commit()
            return n
    except Exception as e:
        logger.error("actualizar_num_lineas: %s", e)
        return 0


def listar_lineas(id_extracto, *, solo_no_conciliadas=False, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM extracto_lineas WHERE id_extracto=%s AND id_empresa=%s"
    p = [id_extracto, id_empresa]
    if solo_no_conciliadas:
        q += " AND conciliado=0"
    q += " ORDER BY fecha, id"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("listar_lineas: %s", e)
        return []


def marcar_conciliada(id_linea, id_movimiento, tipo="manual", *, diferencia=0.0,
                      usuario=None, id_empresa=None) -> bool:
    """Marca la línea como conciliada, la enlaza al movimiento y registra la conciliación.

    Atómico y a prueba de DOBLE conciliación: comprueba bajo bloqueo que la línea no esté ya
    conciliada y que el movimiento no esté ya emparejado; el INSERT en conciliaciones está
    además respaldado por UNIQUE(empresa,línea) y UNIQUE(empresa,movimiento) (migr 0051)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT conciliado FROM extracto_lineas WHERE id=%s AND id_empresa=%s FOR UPDATE",
                        (id_linea, id_empresa))
            r = cur.fetchone()
            if not r:
                return False
            if (r[0] if not isinstance(r, dict) else list(r.values())[0]):
                logger.info("marcar_conciliada: línea %s ya conciliada", id_linea)
                return False
            cur.execute("SELECT 1 FROM conciliaciones WHERE id_empresa=%s AND id_movimiento=%s LIMIT 1",
                        (id_empresa, id_movimiento))
            if cur.fetchone():
                logger.info("marcar_conciliada: movimiento %s ya emparejado", id_movimiento)
                return False
            cur.execute("INSERT INTO conciliaciones (id_empresa, id_linea, id_movimiento, tipo, "
                        "diferencia, usuario) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_linea, id_movimiento, tipo, round(float(diferencia or 0), 2), usuario))
            cur.execute("UPDATE extracto_lineas SET conciliado=1, id_movimiento=%s "
                        "WHERE id=%s AND id_empresa=%s", (id_movimiento, id_linea, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        # Choque con UNIQUE (carrera) → conciliación ya existente: no es un error.
        logger.info("marcar_conciliada (posible duplicado evitado): %s", e)
        return False


def movimientos_ya_conciliados(id_empresa) -> set:
    """IDs de movimientos de tesorería ya emparejados (para no reutilizarlos)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_movimiento FROM conciliaciones WHERE id_empresa=%s", (id_empresa,))
            return {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    except Exception as e:
        logger.error("movimientos_ya_conciliados: %s", e)
        return set()
