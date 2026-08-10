"""
Tests CCP Fase II — un fichero por conveniencia, funciones por bloque (B1…B10).

Cada bloque valida su servicio (API-First, sin PyQt) y el aislamiento multiempresa. Se ampliará a
medida que se implementan los bloques.
"""

import pytest

EMP = "T-CCP2-A"
EMP_B = "T-CCP2-B"


# ── B1 · Corporate Templates Manager ──────────────────────────────────────────
def test_b1_templates_versionado_render(db):
    from src.services.ccp import templates as T
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ccp_plantillas WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        cur.execute("DELETE FROM ccp_plantillas_versiones WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()
    pid = T.crear_plantilla("bienvenida", "Hola {{nombre}}", "Estimado {{nombre}}, bienvenido.",
                            id_empresa=EMP, categoria="general", idioma="es")
    assert pid
    # Nueva versión + historial + comparación.
    v = T.nueva_version(pid, "Hola {{nombre}}", "Estimado {{nombre}}, le damos la bienvenida.",
                        id_empresa=EMP)
    assert v == 2
    assert len(T.listar_versiones(pid)) == 2
    diff = T.comparar_versiones(pid, 1, 2)
    assert diff and "bienvenid" in diff
    # Estado producción + render con variables.
    assert T.cambiar_estado(pid, "produccion")
    asunto, cuerpo = T.render("bienvenida", {"nombre": "Ana"}, id_empresa=EMP)
    assert asunto == "Hola Ana" and "Ana" in cuerpo
    # Export/import.
    data = T.exportar(pid)
    assert data and data["codigo"] == "bienvenida"
    pid2 = T.importar({**data, "codigo": "bienvenida2"}, id_empresa=EMP)
    assert pid2 and pid2 != pid
    # Multiempresa: EMP_B no ve las plantillas de EMP.
    assert T.render("bienvenida", {"nombre": "X"}, id_empresa=EMP_B) in (None,) or \
        not T.listar_plantillas(EMP_B)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ccp_plantillas WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        cur.execute("DELETE FROM ccp_plantillas_versiones WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()


# ── B4 · Communication Timeline + Conversation ────────────────────────────────
def test_b4_timeline_conversacion(db):
    from src.db import correo as correo_db
    from src.services import ccp
    bid = correo_db.crear_correo("plataforma@ccp2.com", proveedor="simulado", tipo="general",
                                 id_empresa=EMP)
    correo_db.actualizar_correo(bid, estado="activo")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ccp_comunicaciones WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM ccp_conversaciones WHERE id_empresa=%s", (EMP,))
        conn.commit()
    # Dos comunicaciones al mismo contacto → mismo hilo.
    r1 = ccp.enviar_comunicacion(id_empresa=EMP, destinatario="cli@x.com", asunto="Hilo 1", cuerpo="a")
    r2 = ccp.enviar_comunicacion(id_empresa=EMP, destinatario="cli@x.com", asunto="Hilo 2", cuerpo="b")
    assert r1.ok and r2.ok
    msgs = ccp.conversaciones.listar_conversaciones(EMP, correo="cli@x.com")
    assert msgs and msgs[0]["n_mensajes"] == 2
    # Timeline unificado (2 salientes).
    tl = ccp.timeline.timeline(EMP, correo="cli@x.com")
    assert len([e for e in tl if e["sentido"] == "saliente"]) == 2
    # Agrupado por conversación.
    grupos = ccp.timeline.timeline_agrupado(EMP, correo="cli@x.com")
    assert grupos and len(grupos[0]["eventos"]) == 2
    correo_db.eliminar_correo(bid)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ccp_comunicaciones WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM ccp_conversaciones WHERE id_empresa=%s", (EMP,))
        conn.commit()


# ── B3 · Campaign Manager + Outgoing Queue ────────────────────────────────────
def test_b3_campana_cola(db):
    from src.db import correo as correo_db
    from src.services import ccp
    bid = correo_db.crear_correo("plataforma@ccp3.com", proveedor="simulado", tipo="general",
                                 id_empresa=EMP)
    correo_db.actualizar_correo(bid, estado="activo")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("ccp_campanas", "ccp_campana_destinatarios", "ccp_cola"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()
    cid = ccp.campanas.crear_campana("Aviso mantenimiento", id_empresa=EMP, tipo="mantenimiento",
                                     asunto="Aviso", cuerpo="Texto",
                                     destinatarios=["a@x.com", "b@x.com", {"correo": "c@x.com"}])
    assert cid
    st = ccp.campanas.estadisticas(cid)
    assert st["total"] == 3 and st["pendientes"] == 3
    # Pausada no procesa.
    ccp.campanas.pausar(cid)
    assert ccp.campanas.procesar_campana(cid) == 0
    ccp.campanas.reanudar(cid)
    # Procesa por la Outgoing Queue.
    n = ccp.campanas.procesar_campana(cid)
    assert n == 3
    st2 = ccp.campanas.estadisticas(cid)
    assert st2["enviados"] == 3 and st2["pendientes"] == 0 and st2["estado"] == "finalizada"
    correo_db.eliminar_correo(bid)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("ccp_campanas", "ccp_campana_destinatarios", "ccp_cola", "ccp_comunicaciones",
                  "ccp_conversaciones"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()


# ── B5 · Analytics / B6 · Notification Center / B10 · Governance ──────────────
def test_b5_b6_b10(db):
    from src.db import correo as correo_db
    from src.services import ccp
    bid = correo_db.crear_correo("plataforma@ccp5.com", proveedor="simulado", tipo="general",
                                 id_empresa=EMP)
    correo_db.actualizar_correo(bid, estado="activo")
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("ccp_comunicaciones", "ccp_conversaciones", "ccp_consentimientos",
                  "ccp_politicas_comunicacion"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()
    # Envíos → analítica.
    ccp.enviar_comunicacion(id_empresa=EMP, destinatario="ok1@x.com", asunto="a", cuerpo="b")
    ccp.enviar_comunicacion(id_empresa=EMP, destinatario="ok2@x.com", asunto="a", cuerpo="b")
    res = ccp.analitica.resumen(EMP)
    assert res["total"] >= 2 and res["por_canal"].get("email", 0) >= 2 and res["tasa_exito"] > 0

    # B10 · lista negra bloquea el envío (asociado al com_id).
    ccp.gobierno.anadir_politica("lista_negra", "malo@x.com", id_empresa=EMP)
    r = ccp.enviar_comunicacion(id_empresa=EMP, destinatario="malo@x.com", asunto="a", cuerpo="b")
    assert not r.ok and "gobierno" in r.mensaje.lower() and r.com_id
    # Consentimiento revocado también bloquea.
    ccp.gobierno.registrar_consentimiento("revocado@x.com", id_empresa=EMP, canal="email",
                                          estado="revocado")
    r2 = ccp.enviar_comunicacion(id_empresa=EMP, destinatario="revocado@x.com", asunto="a", cuerpo="b")
    assert not r2.ok

    # B6 · Notification Center: externa por el Communication Service.
    out = ccp.notificaciones_centro.notificar("Aviso", "Cuerpo", id_empresa=EMP,
                                              destinatario="ext@x.com")
    assert out["externa"] and out["externa"]["ok"]
    correo_db.eliminar_correo(bid)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("ccp_comunicaciones", "ccp_conversaciones", "ccp_consentimientos",
                  "ccp_politicas_comunicacion"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()


# ── B8 · Omnichannel (degradable) ─────────────────────────────────────────────
def test_b8_omnichannel_degradable(db):
    from src.services import ccp
    claves = {c.clave for c in ccp.canales.canales()}
    assert {"whatsapp", "sms", "push", "teams", "slack", "telegram", "firma"} <= claves
    # Sin credenciales configuradas → no operativos y no envían de verdad.
    for clave in ("whatsapp", "sms", "telegram", "teams", "slack", "push", "firma"):
        c = ccp.canales.canal(clave)
        assert not c.disponible()
    from src.services.ccp.modelo import Comunicacion
    r = ccp.canales.canal("telegram").enviar(Comunicacion(id_empresa=EMP,
                                             destinatarios=["123"], com_id="COM-X"))
    assert not r.ok and r.estado == "no_operativo"
    # El único operativo sigue siendo email.
    assert [c.clave for c in ccp.canales.canales() if c.disponible()] == ["email"]


# ── B2 · Workflow Communication Engine ────────────────────────────────────────
def test_b2_workflow(db):
    from src.db import correo as correo_db
    from src.services import ccp
    bid = correo_db.crear_correo("plataforma@ccp2wf.com", proveedor="simulado", tipo="general",
                                 id_empresa=EMP)
    correo_db.actualizar_correo(bid, estado="activo")
    assert "factura_pendiente" in ccp.workflows.flujos()
    # Flujo simple: enviar si condición se cumple.
    ccp.workflows.registrar_flujo("test_flow", [
        {"tipo": "enviar", "asunto": "Aviso", "cuerpo": "Cuerpo"},
        {"tipo": "condicion", "clave": "pendiente", "op": "==", "valor": True},
        {"tipo": "notificar", "titulo": "Pendiente", "mensaje": "x", "roles": ["ADMINISTRADOR"]},
    ])
    r = ccp.workflows.ejecutar_flujo("test_flow", {"pendiente": True}, id_empresa=EMP,
                                     destinatario="wf@x.com")
    tipos = [p["tipo"] for p in r["traza"]]
    assert r["ok"] and "enviar" in tipos and any(p.get("com_id") for p in r["traza"])
    # Condición NO cumplida corta el flujo.
    r2 = ccp.workflows.ejecutar_flujo("test_flow", {"pendiente": False}, id_empresa=EMP,
                                      destinatario="wf@x.com")
    assert r2["detenido_en"] is not None
    correo_db.eliminar_correo(bid)


# ── B7 · Corporate Contacts CRM ───────────────────────────────────────────────
def test_b7_crm_jerarquias(db):
    from src.services import ccp
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ccp_relaciones WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()
    ccp.contactos_crm.vincular("departamento", "D1", "empresa", "E1", rol="pertenece_a", id_empresa=EMP)
    ccp.contactos_crm.vincular("persona", "P1", "departamento", "D1", rol="pertenece_a", id_empresa=EMP)
    ccp.contactos_crm.vincular("persona", "P2", "departamento", "D1", rol="responsable", id_empresa=EMP)
    # Árbol desde la empresa.
    arbol = ccp.contactos_crm.arbol("empresa", "E1", id_empresa=EMP)
    assert arbol["hijos"] and arbol["hijos"][0]["id"] == "D1"
    assert len(arbol["hijos"][0]["hijos"]) == 1   # solo P1 (pertenece_a); P2 es responsable
    resp = ccp.contactos_crm.responsables("persona", "P2", id_empresa=EMP)
    assert resp and resp[0]["rol"] == "responsable"
    # Multiempresa.
    assert ccp.contactos_crm.relaciones("empresa", "E1", id_empresa=EMP_B) == []
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ccp_relaciones WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
        conn.commit()


# ── B9 · IA Communication Assistant (degradable) ──────────────────────────────
def test_b9_ia_asistente():
    from src.services import ccp
    ia = ccp.ia_asistente
    assert ia.generar_asunto("Recordatorio de pago. Segundo párrafo.") == "Recordatorio de pago."
    assert ia.clasificar("Su factura está pendiente") == "facturacion"
    ext = ia.extraer("Contacto: a@b.com y 600123123 por 50,00 €")
    assert "a@b.com" in ext["correos"] and ext["importes"]
    red = ia.redactar("Aviso de mantenimiento", contexto={"fecha": "12/07"})
    assert red["asunto"] and "mantenimiento" in red["cuerpo"].lower()
    assert ia.corregir("Hola   ,  mundo .") == "Hola, mundo."


# ── API-First: los servicios CCP no importan PyQt ─────────────────────────────
def test_apifirst_servicios_sin_pyqt():
    import importlib
    import pkgutil
    import src.services.ccp as ccp_pkg
    ofensores = []
    for mod in pkgutil.walk_packages(ccp_pkg.__path__, prefix="src.services.ccp."):
        name = mod.name
        try:
            m = importlib.import_module(name)
        except Exception:
            continue
        src = getattr(m, "__file__", None)
        if not src:
            continue
        with open(src, encoding="utf-8") as f:
            txt = f.read()
        if "PyQt6" in txt or "PyQt5" in txt:
            ofensores.append(name)
    assert ofensores == [], f"servicios CCP con PyQt (rompe API-First): {ofensores}"
