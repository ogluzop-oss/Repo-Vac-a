"""
CRM · Campañas comerciales / Marketing (Módulo 1, enriquecimiento). Gestión de campañas: creación,
segmentación de destinatarios (reutiliza clientes/leads existentes), ejecución por canal (reutiliza el
sistema de correo/comunicaciones), resultados y cierre. Integra auditoría + Event Bus (para SOMA/BI/
Workflow) + BI. NO duplica lógica: se apoya en clientes, leads y correo ya existentes.
"""

import json
import logging

logger = logging.getLogger("crm.campanias")

ESTADOS = ("BORRADOR", "ACTIVA", "PAUSADA", "FINALIZADA", "CANCELADA")


def _emp(id_empresa=None):
    # IOC v3 (Bloque V): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.crm.identidad_crm import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("crm", accion, "crm_campanias", (detalle or "")[:255])
    except Exception:
        pass


def _evento(nombre, payload):
    try:
        from src.services import eventos
        eventos.publicar(nombre, ref_entidad="crm_campania", ref_id=(payload or {}).get("id"),
                         id_empresa=(payload or {}).get("id_empresa"), payload=payload)
    except Exception:
        pass


def crear_campania(nombre, *, canal="email", segmento_objetivo=None, presupuesto=0,
                   fecha_inicio=None, fecha_fin=None, responsable=None, asunto=None, cuerpo=None,
                   id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO crm_campanias (id_empresa, nombre, canal, segmento_objetivo, "
                        "presupuesto, fecha_inicio, fecha_fin, responsable, asunto, cuerpo) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, nombre[:160], canal, segmento_objetivo, float(presupuesto or 0),
                         fecha_inicio, fecha_fin, responsable, (asunto or None), (cuerpo or None)))
            cid = cur.lastrowid
            c.commit()
        _audit("CAMPANA_CREADA", f"{cid}:{nombre}")
        _evento("crm.campana_creada", {"id": cid, "id_empresa": emp})
        return cid
    except Exception as e:
        logger.error("crear_campania: %s", e)
        return None


def añadir_destinatarios_por_segmento(id_campania, segmento=None, *, incluir_leads=True,
                                       id_empresa=None) -> int:
    """Añade como destinatarios los CLIENTES del segmento indicado (reutiliza la tabla clientes) Y,
    si `incluir_leads` (petición explícita: "a los leads/clientes"), también los LEADS activos con
    email — los leads no tienen un campo "segmento" propio, así que se incluyen todos los que no
    estén ya convertidos/perdidos, al margen del segmento pedido para clientes. Idempotente: nunca
    duplica un destinatario ya presente en la campaña."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_cliente, id_lead FROM crm_campania_destinatarios "
                        "WHERE id_campania=%s", (id_campania,))
            ya = {(f.get("id_cliente"), f.get("id_lead")) for f in _filas_a_dicts(cur, cur.fetchall())}

            q = "SELECT id FROM clientes WHERE id_empresa<=>%s AND estado='activo'"
            p = [emp]
            if segmento:
                q += " AND segmento=%s"; p.append(segmento)
            cur.execute(q, p)
            ids_cliente = [f["id"] for f in _filas_a_dicts(cur, cur.fetchall())
                          if (f["id"], None) not in ya]
            for cli in ids_cliente:
                cur.execute("INSERT INTO crm_campania_destinatarios (id_campania, id_cliente) "
                            "VALUES (%s,%s)", (id_campania, cli))

            ids_lead = []
            if incluir_leads:
                cur.execute(
                    "SELECT id FROM crm_leads WHERE id_empresa<=>%s "
                    "AND estado NOT IN ('convertido','perdido') AND email IS NOT NULL AND email<>''",
                    (emp,))
                ids_lead = [f["id"] for f in _filas_a_dicts(cur, cur.fetchall())
                           if (None, f["id"]) not in ya]
                for lead in ids_lead:
                    cur.execute("INSERT INTO crm_campania_destinatarios (id_campania, id_lead) "
                                "VALUES (%s,%s)", (id_campania, lead))
            c.commit()
        total = len(ids_cliente) + len(ids_lead)
        _audit("CAMPANA_DESTINATARIOS", f"{id_campania}:+{total}")
        return total
    except Exception as e:
        logger.error("añadir_destinatarios: %s", e)
        return 0


def enviar_campania(id_campania, *, id_empresa=None) -> dict:
    """Disparo REAL de la campaña por correo (petición explícita) — reutiliza la Corporate
    Communication Platform (`services.ccp.enviar_comunicacion`, el MISMO motor que usa todo el
    resto de la app, nunca un envío paralelo). Resuelve/completa automáticamente los destinatarios
    del segmento (clientes + leads) si la campaña aún no los tenía, envía a los que sigan
    PENDIENTE, y marca cada uno CONTACTADO (enviado) o FALLIDO (la campaña puede re-lanzarse: solo
    reintenta los PENDIENTE/FALLIDO, nunca reenvía a quien ya está CONTACTADO).

    Honesto: solo "email" tiene infraestructura de envío real hoy (igual que el resto de canales de
    `services.ccp`); otro canal devuelve ok=False con el motivo, sin fingir un envío que no existe.
    """
    emp = _emp(id_empresa)
    from src.db.conexion import _fila_a_dict, _filas_a_dicts, obtener_conexion
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM crm_campanias WHERE id=%s AND id_empresa<=>%s",
                        (id_campania, emp))
            camp = _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("enviar_campania (leer): %s", e)
        return {"ok": False, "motivo": str(e), "enviados": 0, "fallidos": 0, "total": 0}
    if not camp:
        return {"ok": False, "motivo": "Campaña no encontrada.", "enviados": 0, "fallidos": 0, "total": 0}
    if (camp.get("canal") or "email") != "email":
        return {"ok": False, "motivo": f"El canal '{camp.get('canal')}' todavía no tiene envío real "
                                       f"implementado (solo 'email').", "enviados": 0, "fallidos": 0, "total": 0}
    asunto, cuerpo = camp.get("asunto"), camp.get("cuerpo")
    if not (asunto and cuerpo):
        return {"ok": False, "motivo": "Falta el asunto y/o el cuerpo del correo de la campaña.",
                "enviados": 0, "fallidos": 0, "total": 0}

    # Completa destinatarios la primera vez (idempotente — no duplica si ya se había llamado).
    añadir_destinatarios_por_segmento(id_campania, camp.get("segmento_objetivo"), id_empresa=emp)

    from src.services import ccp
    enviados = fallidos = 0
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "SELECT d.id, d.id_cliente, d.id_lead, "
                "COALESCE(cli.email, lead.email) AS email "
                "FROM crm_campania_destinatarios d "
                "LEFT JOIN clientes cli ON cli.id=d.id_cliente "
                "LEFT JOIN crm_leads lead ON lead.id=d.id_lead "
                "WHERE d.id_campania=%s AND d.estado IN ('PENDIENTE','FALLIDO')", (id_campania,))
            destinatarios = _filas_a_dicts(cur, cur.fetchall())
        for d in destinatarios:
            email = (d.get("email") or "").strip()
            nuevo_estado = "FALLIDO"
            if email and "@" in email:
                try:
                    res = ccp.enviar_comunicacion(destinatario=email, asunto=asunto, cuerpo=cuerpo,
                                                  canal="email", contexto="crm")
                    if res.ok:
                        nuevo_estado = "CONTACTADO"
                        enviados += 1
                    else:
                        fallidos += 1
                except Exception as e:
                    logger.debug("enviar_campania destinatario %s: %s", d.get("id"), e)
                    fallidos += 1
            else:
                fallidos += 1
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE crm_campania_destinatarios SET estado=%s WHERE id=%s",
                            (nuevo_estado, d["id"]))
                c.commit()
    except Exception as e:
        logger.error("enviar_campania (enviar): %s", e)
        return {"ok": False, "motivo": str(e), "enviados": enviados, "fallidos": fallidos,
                "total": enviados + fallidos}
    total = enviados + fallidos
    _audit("CAMPANA_ENVIADA", f"{id_campania}: {enviados} ok / {fallidos} fallidos de {total}")
    _evento("crm.campana_enviada", {"id": id_campania, "id_empresa": emp,
                                    "enviados": enviados, "fallidos": fallidos})
    return {"ok": True, "enviados": enviados, "fallidos": fallidos, "total": total}


def activar(id_campania, *, id_empresa=None) -> dict:
    """Marca la campaña ACTIVA y DISPARA el envío real por correo a sus destinatarios (petición
    explícita) — reutiliza `enviar_campania`/la Corporate Communication Platform, nunca un motor de
    envío paralelo. El estado se marca ACTIVA tanto si el envío tiene éxito como si falla (p. ej.
    falta contenido): "activar" es un cambio de estado válido en sí mismo; el detalle del envío
    viaja en el resultado para que la UI lo muestre."""
    res_estado = _set_estado(id_campania, "ACTIVA", id_empresa=id_empresa)
    if not res_estado.get("ok"):
        return res_estado
    res_envio = enviar_campania(id_campania, id_empresa=id_empresa)
    return {**res_estado, **res_envio}


def _set_estado(id_campania, estado, *, id_empresa=None) -> dict:
    if estado not in ESTADOS:
        return {"ok": False, "motivo": "estado inválido"}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE crm_campanias SET estado=%s WHERE id=%s", (estado, id_campania))
            c.commit()
        _audit("CAMPANA_ESTADO", f"{id_campania}={estado}")
        _evento("crm.campana_estado", {"id": id_campania, "estado": estado})
        return {"ok": True, "estado": estado}
    except Exception as e:
        logger.error("_set_estado: %s", e)
        return {"ok": False, "motivo": str(e)}


def resultados(id_campania) -> dict:
    """Métricas de la campaña: nº destinatarios, contactados, convertidos (reutiliza destinatarios)."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT estado, COUNT(*) n FROM crm_campania_destinatarios "
                        "WHERE id_campania=%s GROUP BY estado", (id_campania,))
            por = {f["estado"]: int(f["n"]) for f in _filas_a_dicts(cur, cur.fetchall())}
        total = sum(por.values())
        return {"total": total, "por_estado": por,
                "convertidos": por.get("CONVERTIDO", 0), "contactados": por.get("CONTACTADO", 0)}
    except Exception as e:
        logger.debug("resultados: %s", e)
        return {"total": 0, "por_estado": {}}


def listar(id_empresa=None, *, limite=100) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM crm_campanias WHERE id_empresa<=>%s ORDER BY creada DESC LIMIT %s",
                        (emp, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar campañas: %s", e)
        return []
