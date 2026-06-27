"""
Dashboard DR (DR-E) + Runbook DR (DR-F).

panel() agrega el estado real de DR (ultimo backup, ultima verificacion, ultimo restore test,
RPO/RTO, replicacion, almacenamiento, incidentes DR) reutilizando observabilidad y los servicios DR.
runbook() genera documentacion de recuperacion exportable a JSON/HTML (PDF si reportlab esta).
"""

import datetime as _dt
import json
import logging
import os

logger = logging.getLogger("dr.dashboard")


def panel(id_empresa=None) -> dict:
    from src.services.dr import dr_drills, dr_pitr, dr_replicacion, dr_storage
    snaps = dr_pitr.listar_snapshots(limite=1)
    verify = dr_drills.ultimos("verify_diario", 1)
    restore = dr_drills.ultimos("restore_test_semanal", 1)
    incidentes = []
    try:
        from src.services.seguridad import incidentes as _inc
        incidentes = [i for i in _inc.listar(id_empresa=id_empresa) if "DR" in (i.get("detalle") or "")][:5]
    except Exception:
        pass
    backend_cod = dr_storage.backend().codigo
    edad = None
    try:
        from src.db import backup
        edad = backup.edad_ultimo_backup_horas()
    except Exception:
        pass
    return {
        "ultimo_backup_horas": edad,
        "ultimo_snapshot": snaps[0] if snaps else None,
        "ultima_verificacion": verify[0] if verify else None,
        "ultimo_restore_test": restore[0] if restore else None,
        "rpo": dr_pitr.calcular_rpo(),
        "rto": dr_pitr.calcular_rto(),
        "replicacion": dr_replicacion.estado_replicacion(),
        "almacenamiento": {"backend": backend_cod},
        "incidentes_dr": incidentes,
    }


# ── Runbook DR (DR-F) ─────────────────────────────────────────────────────────
_SECCIONES = [
    ("Backup", "Backups completos via db/backup.crear_backup (mysqldump + export logico). "
               "Retencion por mtime. Programado por Scheduler (job 'backup', 24h)."),
    ("Restore global", "db/backup.restaurar_backup(ruta). Verificable con verificar_backup "
                       "(restore a BD temporal). RTO objetivo < 1h."),
    ("PITR", "services/dr/dr_pitr: crear_snapshot / restaurar_a_timestamp / restaurar_a_snapshot. "
             "Aproxima al snapshot anterior al instante. PITR fino requiere binlog de MariaDB."),
    ("Replica / Failover", "services/dr/dr_replicacion: estado_replicacion / promover_replica. "
                           "Configurar SM_DR_REPLICA_HOST + MariaDB replication. Failover manual."),
    ("Recuperacion tenant", "services/saas/backup_tenant: exportar_empresa / restaurar_empresa "
                            "(por id_empresa, transaccional)."),
    ("Recuperacion global", "restaurar_backup del ultimo snapshot completo. Validar con drills."),
    ("Off-site", "services/dr/dr_storage: backends local/s3/azure/gcs/object (SM_DR_STORAGE)."),
    ("Drills", "services/dr/dr_drills: verify diario, restore test semanal, consistencia mensual."),
]


def runbook(formato="json") -> dict:
    """Genera el runbook de DR en el formato indicado (json|html|pdf). Devuelve {ok, ruta|contenido}."""
    base = os.path.join("documentos", "dr")
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("dr")
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    data = {"titulo": "Runbook Disaster Recovery — Smart Manager AI",
            "generado": _dt.datetime.now().isoformat(),
            "secciones": [{"titulo": t, "contenido": c} for t, c in _SECCIONES]}

    if formato == "json":
        ruta = os.path.join(base, f"runbook_dr_{ts}.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "ruta": ruta, "formato": "json"}

    if formato == "html":
        ruta = os.path.join(base, f"runbook_dr_{ts}.html")
        cuerpo = "".join(f"<h2>{s['titulo']}</h2><p>{s['contenido']}</p>" for s in data["secciones"])
        html = f"<!doctype html><html><head><meta charset='utf-8'><title>{data['titulo']}</title></head>" \
               f"<body><h1>{data['titulo']}</h1><p><i>{data['generado']}</i></p>{cuerpo}</body></html>"
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(html)
        return {"ok": True, "ruta": ruta, "formato": "html"}

    if formato == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            ruta = os.path.join(base, f"runbook_dr_{ts}.pdf")
            c = canvas.Canvas(ruta, pagesize=A4)
            y = 800
            c.setFont("Helvetica-Bold", 14); c.drawString(40, y, data["titulo"]); y -= 30
            c.setFont("Helvetica", 9)
            for s in data["secciones"]:
                c.setFont("Helvetica-Bold", 11); c.drawString(40, y, s["titulo"]); y -= 16
                c.setFont("Helvetica", 9)
                for linea in _wrap(s["contenido"], 95):
                    c.drawString(50, y, linea); y -= 12
                    if y < 60:
                        c.showPage(); y = 800
                y -= 8
            c.save()
            return {"ok": True, "ruta": ruta, "formato": "pdf"}
        except Exception as e:
            logger.warning("runbook pdf no disponible (%s); degrada a json", e)
            return runbook("json")

    return {"ok": False, "error": "formato no soportado"}


def _wrap(txt, n):
    palabras, linea, out = txt.split(), "", []
    for p in palabras:
        if len(linea) + len(p) + 1 > n:
            out.append(linea); linea = p
        else:
            linea = f"{linea} {p}".strip()
    if linea:
        out.append(linea)
    return out
