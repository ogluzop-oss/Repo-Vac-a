"""
Seguridad avanzada (Bloque SEC) — MFA TOTP, recovery codes, sesiones, anomalías, guard tenant,
secret manager y RGPD (acceso/portabilidad/olvido).
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


# ── SEC-1 MFA TOTP ────────────────────────────────────────────────────────────
def test_mfa_totp_ciclo(db):
    from src.services.seguridad import mfa
    uid = 880001
    try:
        ini = mfa.iniciar_activacion(uid, "user@acme")
        assert ini["secreto"] and ini["uri"].startswith("otpauth://")
        # código inválido no activa
        assert mfa.confirmar_activacion(uid, "000000")["ok"] is False
        codigo = mfa.codigo_actual(ini["secreto"])
        r = mfa.confirmar_activacion(uid, codigo)
        assert r["ok"] and len(r["recovery_codes"]) == 8
        assert mfa.mfa_activo(uid) is True
        # verificación de segundo factor
        assert mfa.verificar(uid, mfa.codigo_actual(ini["secreto"])) is True
        assert mfa.verificar(uid, "111111") is False
        # SEC-2 recovery code de un solo uso
        rc = r["recovery_codes"][0]
        assert mfa.usar_recovery_code(uid, rc) is True
        assert mfa.usar_recovery_code(uid, rc) is False    # ya usado
        mfa.desactivar(uid)
        assert mfa.mfa_activo(uid) is False
        # MFA no activo → verificar permite (compat)
        assert mfa.verificar(uid, "cualquier") is True
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (uid,))
            cur.execute("DELETE FROM mfa_usuarios WHERE id_usuario=%s", (uid,))
            conn.commit()


# ── SEC-4 Anomalías → incidente ──────────────────────────────────────────────
def test_anomalias_fuerza_bruta(db):
    from src.services.seguridad import anomalias
    from src.db.conexion import log_auditoria
    nif = "BRUTE" + uuid.uuid4().hex[:5]
    for _ in range(6):
        log_auditoria(nif, "LOGIN_FALLIDO", "seguridad", "intento", "1.2.3.4")
    try:
        inc = anomalias.detectar_fuerza_bruta(umbral=5, ventana_min=60, id_empresa=E)
        assert any(inc)        # se abrió al menos un incidente
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM eventos_incidentes WHERE id_incidente IN "
                        "(SELECT id FROM incidentes_seguridad WHERE tipo='fuerza_bruta' AND ip_origen='1.2.3.4')")
            cur.execute("DELETE FROM incidentes_seguridad WHERE tipo='fuerza_bruta' AND ip_origen='1.2.3.4'")
            cur.execute("DELETE FROM auditoria_logs WHERE usuario=%s", (nif,))
            conn.commit()


# ── SEC-6 Guard central de tenant (analizador) ───────────────────────────────
def test_tenant_guard():
    from src.services.seguridad import tenant_guard as TG
    assert TG.es_segura("SELECT * FROM ventas WHERE id_empresa=%s") is True
    assert TG.es_segura("SELECT * FROM ventas WHERE codigo=%s") is False     # tabla tenant sin filtro
    assert TG.es_segura("SELECT * FROM permisos") is True                    # tabla no-tenant
    a = TG.analizar("SELECT * FROM clientes c JOIN ventas v ON v.cliente_id=c.id")
    assert a["ok"] is False and "ventas" in a["tablas_tenant"]


def test_aislamiento_schema(db):
    from src.services.saas import aislamiento as AIS
    assert AIS.verificar("ventas") and AIS.verificar("notificaciones")


# ── SEC-7 Secret manager ──────────────────────────────────────────────────────
def test_secret_manager():
    from src.services.seguridad import secret_manager as SM
    tok = SM.cifrar("clave-super-secreta")
    assert tok and SM.descifrar(tok) == "clave-super-secreta"
    assert SM.descifrar(SM.rotar(tok)) == "clave-super-secreta"   # rotación conserva el valor


# ── SEC-9 RGPD ────────────────────────────────────────────────────────────────
def test_rgpd_acceso_y_olvido(db):
    from src.services.seguridad import rgpd
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO clientes (nombre, nif, email, id_empresa) VALUES (%s,%s,%s,%s)",
                    ("Juan Personal", "12345678Z", "juan@x.com", E))
        cid = cur.lastrowid
        cur.execute("INSERT INTO ventas (fecha, total, id_empresa, cliente_id, cliente_nombre, cliente_nif) "
                    "VALUES (NOW(), 50, %s, %s, 'Juan Personal', '12345678Z')", (E, cid))
        vid = cur.lastrowid
        conn.commit()
    try:
        acc = rgpd.acceso(cid, id_empresa=E, solicitante="dpo")
        assert acc["ok"] and os.path.exists(acc["ruta"])
        os.remove(acc["ruta"])
        olv = rgpd.olvido(cid, id_empresa=E, solicitante="dpo")
        assert olv["ok"] and olv["registros_anonimizados"] >= 1
        # verifica anonimización
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nif, email FROM clientes WHERE id=%s", (cid,))
            r = cur.fetchone(); assert r[0] is None and r[1] is None
            cur.execute("SELECT cliente_nif FROM ventas WHERE id=%s", (vid,))
            assert cur.fetchone()[0] is None
        assert any(s["tipo"] == "olvido" for s in rgpd.listar_solicitudes(E))
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ventas WHERE id=%s", (vid,))
            cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
            cur.execute("DELETE FROM rgpd_solicitudes WHERE id_empresa=%s AND sujeto_id=%s", (E, str(cid)))
            conn.commit()
