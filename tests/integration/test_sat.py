"""
SAT/Helpdesk — tickets (ciclo + comentarios), SLA/contratos, colas/asignacion, intervenciones,
KB versionada, email-to-ticket, KPIs e IA (clasificacion/priorizacion/sugerencia). RBAC.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


def _cliente(db, email=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO clientes (nombre, email, id_empresa, estado) VALUES (%s,%s,%s,'activo')",
                    ("Cli", email, E))
        cid = cur.lastrowid
        conn.commit()
    return cid


@pytest.fixture
def limpia(db):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("partes_tecnicos", "intervenciones", "asignaciones_ticket", "ticket_comentarios",
                  "tickets", "contratos_servicio", "sla_servicio", "colas_soporte",
                  "kb_versiones", "kb_articulos", "kb_categorias"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (E,))
        conn.commit()


def test_ticket_ciclo_y_comentarios(db, limpia):
    from src.services.sat import tickets
    tid = tickets.crear_ticket("Fallo", descripcion="No arranca", prioridad="alta", id_empresa=E)
    assert tid
    assert tickets.comentar(tid, "Revisando", autor="tec", id_empresa=E)
    assert tickets.cambiar_estado(tid, "en_proceso", id_empresa=E)["ok"]
    assert tickets.cambiar_estado(tid, "resuelto", id_empresa=E)["ok"]
    assert tickets.cambiar_estado(tid, "reabierto", id_empresa=E)["ok"]   # resuelto->reabierto
    with pytest.raises(ValueError):
        tickets.cambiar_estado(tid, "zzz", id_empresa=E)


def test_sla_y_vencimiento(db, limpia):
    from src.services.sat import contratos_sla, tickets
    cid = _cliente(db)
    sla = contratos_sla.crear_sla(f"S_{uuid.uuid4().hex[:4]}", "Prem", cobertura="premium", id_empresa=E)
    contratos_sla.crear_contrato(cid, cobertura="premium", id_sla=sla, id_empresa=E)
    tid = tickets.crear_ticket("Con SLA", id_cliente=cid, prioridad="critica", id_empresa=E)
    t = tickets.obtener(tid)
    assert t["sla_vencimiento"] is not None and t["id_contrato"]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,)); conn.commit()


def test_sla_incumplido_job(db, limpia):
    from src.services.sat import contratos_sla, tickets
    tid = tickets.crear_ticket("Vencido", prioridad="media", id_empresa=E)
    # fuerza un SLA ya vencido
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE tickets SET sla_vencimiento=(NOW() - INTERVAL 1 HOUR) WHERE id=%s", (tid,))
        conn.commit()
    r = contratos_sla.procesar_sla_tickets(id_empresa=E)
    assert tid in r["incumplidos"]
    assert tickets.obtener(tid)["sla_incumplido"] == 1


def test_colas_autoasignacion(db, limpia):
    from src.services.sat import tickets
    cola = tickets.crear_cola(f"C_{uuid.uuid4().hex[:4]}", "N1", auto_asignar=True, responsable=7, id_empresa=E)
    tid = tickets.crear_ticket("Auto", id_cola=cola, id_empresa=E)
    assert tickets.obtener(tid)["tecnico"] == 7


def test_intervenciones_y_partes(db, limpia):
    from src.services.sat import intervenciones, tickets
    tid = tickets.crear_ticket("Visita", id_empresa=E)
    iv = intervenciones.registrar_intervencion(id_ticket=tid, tecnico=1, tipo="visita", horas=2, id_empresa=E)
    assert iv
    assert intervenciones.crear_parte(iv, "Cambio pieza", firmado=True, id_empresa=E)
    assert len(intervenciones.listar(id_ticket=tid, id_empresa=E)) == 1


def test_kb_versionado_y_busqueda(db, limpia):
    from src.services.sat import kb
    aid = kb.crear_articulo("Reiniciar equipo", "Pasos iniciales", publicado=True, etiquetas="equipo", id_empresa=E)
    assert aid
    assert kb.editar_articulo(aid, "Pasos actualizados", autor="ed", id_empresa=E)
    assert kb.ver_articulo(aid)["version"] == 2
    assert any(a["id"] == aid for a in kb.buscar("reiniciar", id_empresa=E))


def test_email_to_ticket(db, limpia):
    from src.db import correo
    from src.services.sat import email_ticket, tickets
    # correo nuevo -> ticket
    correo.guardar_recibido(1, "user@cli.com", "Necesito ayuda", "No funciona", id_empresa=E)
    r1 = email_ticket.procesar_correos(id_empresa=E)
    assert r1["creados"]
    tid = r1["creados"][0]
    cod = tickets.obtener(tid)["codigo"]
    # respuesta referenciando el ticket -> comentario, no nuevo ticket
    correo.guardar_recibido(1, "user@cli.com", f"Re: {cod} sigo igual", "Nada", id_empresa=E)
    r2 = email_ticket.procesar_correos(id_empresa=E)
    assert tid in r2["actualizados"]


def test_ia_sat(db, limpia):
    from src.services.sat import analitica, kb, tickets
    assert analitica.priorizar("produccion parada urgente") == "critica"
    assert analitica.clasificar("error de login y password") in ("acceso", "tecnico")
    assert analitica.detectar_urgencia("sistema caido") is True
    kb.crear_articulo("Solucion TPV", "Reinicie el TPV", publicado=True, etiquetas="tpv", id_empresa=E)
    tid = tickets.crear_ticket("Problema con el TPV", descripcion="El TPV no responde", id_empresa=E)
    res = analitica.analizar_ticket(tid, aplicar=True, id_empresa=E)
    assert res["ok"] and res["categoria"]
    assert "tickets_abiertos" in analitica.kpis(id_empresa=E)


def test_rbac_sat(db):
    from src.services.seguridad import catalogo
    catalogo.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo IN ('sat.ver','tickets.crear','sla.gestionar','kb.ver')")
        enc = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    assert {"sat.ver", "tickets.crear", "sla.gestionar", "kb.ver"} <= enc
