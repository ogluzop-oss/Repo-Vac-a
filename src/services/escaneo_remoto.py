"""
Escaneo remoto — delegación universal de escaneo QR/código de barras de escritorio al móvil.

Cualquier campo de escritorio que necesite un código (empezando por las barras de búsqueda de
artículo) puede delegar el escaneo al móvil en vez de depender de un diálogo de cámara del PC (torpe:
los 3 que existían usaban la webcam del ordenador, no una cámara real de mano — todos retirados).

DIFUSIÓN POR TIENDA (no por usuario): la solicitud no va dirigida al propio teléfono del mismo
empleado que está en escritorio — se difunde a TODOS los móviles logueados en la MISMA tienda/almacén
(`centro_codigo`, el mismo código de centro que ya lleva el JWT — ver `src/api/security.py`, columna
`usuarios.centro_codigo`), NUNCA a otras tiendas. Cualquier móvil de esa tienda puede reclamarla
(`reclamar_solicitud`, UPDATE atómico condicionado a que nadie la haya reclamado ya); a partir de ahí
solo el que la reclamó puede completarla o cancelarla — el resto deja de verla en el siguiente sondeo.

Resuelto por SONDEO REST corto, sin push ni SSE: el móvil no tiene hoy ningún cliente de tiempo real
(su arquitectura es 100% REST por pull) y no existe infraestructura de "despertar al móvil" (FCM/APNs)
en el proyecto — construir eso sería desproporcionado para una espera de, como mucho, un par de
minutos. El hub SSE existente (`services/eventbus/realtime.py`) tampoco se usa: reparte por tenant, no
por tienda, y no lo consume nadie hoy.
"""

import datetime as _dt
import logging
import uuid

from src.db.conexion import obtener_conexion, transaccion

logger = logging.getLogger("escaneo_remoto")

ESTADOS = ("pendiente", "completado", "cancelado", "expirado")
_TTL_MINUTOS = 3


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_solicitud(id_usuario, *, contexto=None, id_empresa=None, centro_codigo=None,
                    tipo="codigo") -> dict:
    """`centro_codigo` es OBLIGATORIO: sin tienda/almacén no hay a quién difundir la solicitud (un
    usuario sin centro asignado, p. ej. algunos perfiles de administración, no puede usar esta
    delegación desde ese puesto — error honesto, no se inventa un destino). `tipo`: 'codigo' (escanear
    un código de barras/QR, comportamiento original) o 'foto' (el móvil responde con una foto en vez de
    un valor de texto — ver `completar_solicitud`, que en ambos casos solo guarda un `valor` opaco)."""
    if not centro_codigo:
        return {"ok": False, "error": "Tu usuario no tiene tienda/almacén asignado: no hay a quién "
                                       "avisar en el móvil."}
    if tipo not in ("codigo", "foto"):
        tipo = "codigo"
    eid = _emp(id_empresa)
    sid = str(uuid.uuid4())
    expira = _dt.datetime.now() + _dt.timedelta(minutes=_TTL_MINUTOS)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO escaneos_remotos (id, id_empresa, id_usuario, contexto, estado, expira, "
                "centro_codigo, tipo) VALUES (%s,%s,%s,%s,'pendiente',%s,%s,%s)",
                (sid, eid, id_usuario, contexto, expira, centro_codigo, tipo))
        return {"ok": True, "id": sid, "expira": expira.strftime("%Y-%m-%d %H:%M:%S")}
    except Exception as e:
        logger.error("crear_solicitud: %s", e)
        return {"ok": False, "error": str(e)}


def _es_reclamante(fila, id_usuario) -> bool:
    # El `id` del JWT llega SIEMPRE como string (claim "sub"); `id_usuario` es INT en BD — comparar
    # como texto para no fallar por tipo (MySQL coacciona en INSERT/WHERE, pero un `!=` de Python no).
    return fila.get("reclamada_por") is not None and str(fila.get("reclamada_por")) == str(id_usuario)


def _es_propietario(fila, id_usuario) -> bool:
    return str(fila.get("id_usuario")) == str(id_usuario)


def _marcar_expirada_si_toca(fila):
    if fila.get("estado") == "pendiente" and fila.get("expira") and fila["expira"] < _dt.datetime.now():
        try:
            with transaccion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE escaneos_remotos SET estado='expirado' WHERE id=%s AND estado='pendiente'",
                            (fila["id"],))
        except Exception as e:
            logger.error("_marcar_expirada_si_toca: %s", e)
        fila["estado"] = "expirado"
    return fila


def obtener_solicitud(id_solicitud, *, id_empresa=None) -> dict | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM escaneos_remotos WHERE id=%s AND id_empresa=%s",
                        (id_solicitud, eid))
            r = cur.fetchone()
            fila = _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener_solicitud: %s", e)
        return None
    return _marcar_expirada_si_toca(fila) if fila else None


def listar_pendientes_tienda(centro_codigo, *, id_empresa=None) -> list:
    """Solicitudes vivas para difundir en ESTA tienda/almacén: pendientes, sin caducar y que NADIE
    haya reclamado todavía (en cuanto un móvil la reclama, deja de aparecer aquí para el resto)."""
    if not centro_codigo:
        return []
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM escaneos_remotos WHERE id_empresa=%s AND centro_codigo=%s "
                "AND estado='pendiente' AND reclamada_por IS NULL ORDER BY creado DESC",
                (eid, centro_codigo))
            filas = [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_pendientes_tienda: %s", e)
        return []
    vivas = []
    for f in filas:
        f = _marcar_expirada_si_toca(f)
        if f.get("estado") == "pendiente":
            vivas.append(f)
    return vivas


def reclamar_solicitud(id_solicitud, id_usuario, *, id_empresa=None) -> dict:
    """Reclamo ATÓMICO (primero en pulsar "aceptar" se la queda): el UPDATE solo afecta una fila si
    sigue pendiente y NADIE la ha reclamado aún — si `filas_afectadas==0`, alguien ganó la carrera (o
    caducó/canceló entre medias); se informa el motivo real en vez de fallar en silencio."""
    fila = obtener_solicitud(id_solicitud, id_empresa=id_empresa)
    if not fila:
        return {"ok": False, "error": "Solicitud no encontrada.", "motivo": "no_encontrada"}
    if fila.get("estado") != "pendiente":
        motivo = "ya_reclamada" if fila.get("reclamada_por") else fila.get("estado")
        return {"ok": False, "error": f"Solicitud {fila.get('estado')}.", "motivo": motivo}
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE escaneos_remotos SET reclamada_por=%s, reclamada_en=%s "
                "WHERE id=%s AND estado='pendiente' AND reclamada_por IS NULL",
                (id_usuario, _dt.datetime.now(), id_solicitud))
            ganada = cur.rowcount > 0
    except Exception as e:
        logger.error("reclamar_solicitud: %s", e)
        return {"ok": False, "error": str(e)}
    if not ganada:
        return {"ok": False, "error": "Otro dispositivo ya la ha atendido.", "motivo": "ya_reclamada"}
    return {"ok": True}


def completar_solicitud(id_solicitud, valor, id_usuario, *, id_empresa=None) -> dict:
    fila = obtener_solicitud(id_solicitud, id_empresa=id_empresa)
    if not fila:
        return {"ok": False, "error": "Solicitud no encontrada."}
    # La idempotencia (reintento del MISMO dispositivo que la completó) solo aplica a quien la
    # reclamó — comprobar el reclamante ANTES del atajo "ya completada" evita que otro dispositivo
    # de la tienda que nunca la reclamó pueda leer el valor escaneado llamando a este mismo endpoint.
    if not _es_reclamante(fila, id_usuario):
        return {"ok": False, "error": "Esta solicitud no la has reclamado tú."}
    if fila.get("estado") == "completado":
        return {"ok": True, "ya": True, "valor": fila.get("valor_escaneado")}
    if fila.get("estado") != "pendiente":
        return {"ok": False, "error": f"Solicitud {fila.get('estado')}, ya no se puede completar."}
    valor = (valor or "").strip()
    if not valor:
        return {"ok": False, "error": "Valor escaneado vacío."}
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE escaneos_remotos SET estado='completado', valor_escaneado=%s, completado=%s "
                "WHERE id=%s AND estado='pendiente'",
                (valor, _dt.datetime.now(), id_solicitud))
        return {"ok": True, "valor": valor}
    except Exception as e:
        logger.error("completar_solicitud: %s", e)
        return {"ok": False, "error": str(e)}


def cancelar_solicitud(id_solicitud, id_usuario, *, id_empresa=None) -> dict:
    """Cancela quien la creó (escritorio, botón "Cancelar") o quien la reclamó (móvil, si abre la
    cámara y se echa atrás sin escanear — libera la solicitud... salvo que ya esté reclamada, en cuyo
    caso cancelar en vez de liberar es lo correcto: quien creó la solicitud ya sabe que alguien la
    estaba atendiendo, más simple que reabrirla a todo el resto de la tienda otra vez)."""
    fila = obtener_solicitud(id_solicitud, id_empresa=id_empresa)
    if not fila:
        return {"ok": False, "error": "Solicitud no encontrada."}
    if not (_es_propietario(fila, id_usuario) or _es_reclamante(fila, id_usuario)):
        return {"ok": False, "error": "Esta solicitud no te pertenece."}
    if fila.get("estado") != "pendiente":
        return {"ok": True, "ya": True}
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE escaneos_remotos SET estado='cancelado' WHERE id=%s AND estado='pendiente'",
                        (id_solicitud,))
        return {"ok": True}
    except Exception as e:
        logger.error("cancelar_solicitud: %s", e)
        return {"ok": False, "error": str(e)}
