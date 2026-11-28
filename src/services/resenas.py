"""
Reseñas de clientes sobre Smart Manager + comentarios (petición explícita, 2026-11-22): una
sección en "Mi cuenta" del sitio oficial para que los clientes publiquen su opinión, mostrada en
la página de inicio, con comentarios de otros clientes. Tablas `resenas_sitio`/
`resenas_sitio_comentarios` (migración 0357), en la base COMPARTIDA (ver su docstring).

Quién puede escribir: cualquier cuenta de `cuentas_web_central` (clientes con alta web, de pago o
gratuita) — no se exige tener una suscripción activa (una opinión sigue siendo válida aunque el
cliente haya cancelado después). Una reseña por empresa (se edita la existente, nunca se duplica).
Comentarios: cualquier cuenta, múltiples por reseña.

`nombre_mostrado` se resuelve una vez al escribir/comentar (nombre comercial de la empresa, nunca
el email — evita exponer datos de contacto en una página pública) y se guarda tal cual: si la
empresa cambia de nombre después, las reseñas antiguas conservan el nombre de cuando se
escribieron (igual criterio que una factura ya emitida)."""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("services.resenas")

PUNTUACION_MIN = 1
PUNTUACION_MAX = 5
TEXTO_MAX = 2000


def _fila(cur, r):
    if r is None:
        return None
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _filas(cur, rs):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in rs]


def _nombre_para_mostrar(id_empresa) -> str:
    """Nombre comercial de la empresa para mostrar en público — nunca el email. Recurre al
    nombre fiscal si no hay nombre comercial, y a un genérico si no hay ninguno (no debería darse,
    pero una reseña nunca debe fallar por esto)."""
    from src.services import provisioning
    cfg_tenant = provisioning.config_tenant(id_empresa)
    with obtener_conexion(cfg_tenant) as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre_comercial, nombre_empresa FROM empresas WHERE id_empresa=%s",
                   (id_empresa,))
        fila = _fila(cur, cur.fetchone())
    if not fila:
        return "Cliente de Smart Manager"
    return fila.get("nombre_comercial") or fila.get("nombre_empresa") or "Cliente de Smart Manager"


def mi_resena(id_empresa) -> dict | None:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, puntuacion, texto, creado_en, actualizado_en FROM resenas_sitio "
                   "WHERE id_empresa=%s", (id_empresa,))
        return _fila(cur, cur.fetchone())


def publicar_resena(id_empresa, *, puntuacion, texto) -> dict:
    """Crea la reseña de esta empresa o SUSTITUYE la que ya tuviera (nunca duplica)."""
    try:
        puntuacion = int(puntuacion)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Puntuación no válida."}
    if puntuacion < PUNTUACION_MIN or puntuacion > PUNTUACION_MAX:
        return {"ok": False, "error": f"La puntuación debe estar entre {PUNTUACION_MIN} y "
                                      f"{PUNTUACION_MAX}."}
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "error": "Escribe algo en tu reseña."}
    if len(texto) > TEXTO_MAX:
        return {"ok": False, "error": f"La reseña no puede superar los {TEXTO_MAX} caracteres."}

    nombre_mostrado = _nombre_para_mostrar(id_empresa)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO resenas_sitio (id_empresa, nombre_mostrado, puntuacion, texto) "
            "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "nombre_mostrado=VALUES(nombre_mostrado), puntuacion=VALUES(puntuacion), "
            "texto=VALUES(texto)",
            (id_empresa, nombre_mostrado, puntuacion, texto))
        conn.commit()
    logger.info("Reseña publicada/actualizada: empresa=%s puntuacion=%s", id_empresa, puntuacion)
    return {"ok": True}


def eliminar_mi_resena(id_empresa) -> dict:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM resenas_sitio WHERE id_empresa=%s", (id_empresa,))
        fila = _fila(cur, cur.fetchone())
        if not fila:
            return {"ok": True}
        cur.execute("DELETE FROM resenas_sitio_comentarios WHERE id_resena=%s", (fila["id"],))
        cur.execute("DELETE FROM resenas_sitio WHERE id=%s", (fila["id"],))
        conn.commit()
    return {"ok": True}


def listar_resenas(*, limite=None) -> list:
    """Más recientes primero. `limite=None` devuelve todas (página dedicada de opiniones);
    con límite, para la selección breve de la home."""
    sql = ("SELECT id, id_empresa, nombre_mostrado, puntuacion, texto, creado_en FROM "
          "resenas_sitio ORDER BY creado_en DESC")
    args = ()
    if limite:
        sql += " LIMIT %s"
        args = (int(limite),)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        resenas = _filas(cur, cur.fetchall())
        if not resenas:
            return []
        ids = [r["id"] for r in resenas]
        cur.execute(
            f"SELECT id_resena, COUNT(*) AS total FROM resenas_sitio_comentarios "
            f"WHERE id_resena IN ({','.join(['%s'] * len(ids))}) GROUP BY id_resena", ids)
        totales = {f["id_resena"]: f["total"] for f in _filas(cur, cur.fetchall())}
    for r in resenas:
        r["num_comentarios"] = totales.get(r["id"], 0)
    return resenas


def estadisticas() -> dict:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total, AVG(puntuacion) AS media FROM resenas_sitio")
        fila = _fila(cur, cur.fetchone()) or {}
    total = fila.get("total") or 0
    media = float(fila["media"]) if fila.get("media") is not None else 0.0
    return {"total": total, "media": round(media, 1)}


def resena_por_id(id_resena) -> dict | None:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, id_empresa, nombre_mostrado, puntuacion, texto, creado_en "
                   "FROM resenas_sitio WHERE id=%s", (id_resena,))
        return _fila(cur, cur.fetchone())


def listar_comentarios(id_resena) -> list:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, id_empresa, nombre_mostrado, texto, creado_en FROM "
                   "resenas_sitio_comentarios WHERE id_resena=%s ORDER BY creado_en ASC",
                   (id_resena,))
        return _filas(cur, cur.fetchall())


def publicar_comentario(id_resena, id_empresa, *, texto) -> dict:
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "error": "Escribe algo en tu comentario."}
    if len(texto) > TEXTO_MAX:
        return {"ok": False, "error": f"El comentario no puede superar los {TEXTO_MAX} caracteres."}

    if not resena_por_id(id_resena):
        return {"ok": False, "error": "Esta reseña ya no existe."}

    nombre_mostrado = _nombre_para_mostrar(id_empresa)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO resenas_sitio_comentarios (id_resena, id_empresa, nombre_mostrado, texto) "
            "VALUES (%s,%s,%s,%s)", (id_resena, id_empresa, nombre_mostrado, texto))
        conn.commit()
    return {"ok": True}


def eliminar_comentario(id_comentario, id_empresa) -> dict:
    """Solo el autor puede borrar su propio comentario."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM resenas_sitio_comentarios WHERE id=%s AND id_empresa=%s",
                   (id_comentario, id_empresa))
        if not _fila(cur, cur.fetchone()):
            return {"ok": False, "error": "No encontrado."}
        cur.execute("DELETE FROM resenas_sitio_comentarios WHERE id=%s", (id_comentario,))
        conn.commit()
    return {"ok": True}
