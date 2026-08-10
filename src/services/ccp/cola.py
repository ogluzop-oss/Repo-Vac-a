"""
Outgoing Queue — bandeja de salida corporativa de la CCP (CCP Fase II · B3).

Ya NO es solo un hueco: `ColaBD` persiste las comunicaciones pendientes en `ccp_cola` y las despacha
por el Corporate Communication Service (envío síncrono real por lotes). Base de campañas y de envíos
masivos/programados. Multiempresa. API-First (sin PyQt).
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.cola")


class OutgoingQueue:
    """Contrato de una bandeja de salida."""

    def encolar(self, **campos) -> int | None:
        raise NotImplementedError

    def procesar(self, limite: int = 100, *, id_empresa=None) -> int:
        raise NotImplementedError


class ColaBD(OutgoingQueue):
    """Bandeja de salida persistida en `ccp_cola`, despachada por el Communication Service."""

    def encolar(self, *, id_empresa, destinatario, asunto="", cuerpo="", canal="email",
                plantilla_codigo=None, contexto=None, prioridad="normal", id_campana=None,
                programada_para=None, usuario=None) -> int | None:
        try:
            ensure_schema()
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ccp_cola (id_empresa, canal, destinatario, asunto, cuerpo, "
                    "plantilla_codigo, contexto, prioridad, estado, id_campana, programada_para, "
                    "usuario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pendiente',%s,%s,%s)",
                    (id_empresa, canal, destinatario, asunto, cuerpo, plantilla_codigo, contexto,
                     prioridad, id_campana, programada_para, usuario))
                rid = cur.lastrowid
                conn.commit()
                return rid
        except Exception as e:
            logger.debug("encolar: %s", e)
            return None

    def procesar(self, limite: int = 100, *, id_empresa=None) -> int:
        """Despacha las pendientes (respetando prioridad y programación) por el Communication Service.
        Devuelve el nº procesadas. Actualiza estado/intentos y, si hay campaña, sus contadores."""
        try:
            ensure_schema()
            with obtener_conexion() as conn, conn.cursor() as cur:
                q = ("SELECT * FROM ccp_cola WHERE estado='pendiente' AND (programada_para IS NULL OR "
                     "programada_para <= NOW())")
                p = []
                if id_empresa:
                    q += " AND id_empresa=%s"; p.append(id_empresa)
                q += " ORDER BY FIELD(prioridad,'alta','normal','baja'), id LIMIT %s"; p.append(int(limite))
                cur.execute(q, p)
                filas = _filas_a_dicts(cur, cur.fetchall())
        except Exception as e:
            logger.debug("procesar (lectura): %s", e)
            return 0
        from src.services.ccp import servicio as _svc
        n = 0
        for row in filas:
            res = _svc.enviar_comunicacion(
                id_empresa=row.get("id_empresa"), destinatario=row.get("destinatario"),
                asunto=row.get("asunto") or "", cuerpo=row.get("cuerpo") or "",
                plantilla=row.get("plantilla_codigo"), canal=row.get("canal"),
                contexto=row.get("contexto"), usuario=row.get("usuario"))
            estado = "enviado" if res.ok else "fallido"
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE ccp_cola SET estado=%s, com_id=%s, intentos=intentos+1, "
                                "actualizado=NOW() WHERE id=%s", (estado, res.com_id, row["id"]))
                    if row.get("id_campana"):
                        cur.execute("UPDATE ccp_campana_destinatarios SET estado=%s, com_id=%s, "
                                    "actualizado=NOW() WHERE id_campana=%s AND correo=%s",
                                    (estado, res.com_id, row["id_campana"], row.get("destinatario")))
                        campo = "enviados" if res.ok else "fallidos"
                        cur.execute(f"UPDATE ccp_campanas SET {campo}={campo}+1, actualizado=NOW() "
                                    "WHERE id=%s", (row["id_campana"],))
                    conn.commit()
            except Exception as e:
                logger.debug("procesar (actualización): %s", e)
            n += 1
        return n


_cola: OutgoingQueue = ColaBD()


def cola() -> OutgoingQueue:
    return _cola


def set_cola(nueva: OutgoingQueue):
    global _cola
    _cola = nueva
