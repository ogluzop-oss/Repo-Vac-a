"""
Escalado automatico (Paquete Enterprise 7, SUBFASE 7.5). Si una tarea/aprobacion permanece sin
atender 24/48/72 h, escala automaticamente por la cadena de mando (empleado → supervisor →
director → central → administrador). REUTILIZA AutomationService/notificaciones y registra en
`org_escalados` + Auditoria (SUBFASE 7.11). Asincrono (via scheduler).
"""

import logging

logger = logging.getLogger("gobierno.escalado")

_NIVEL_ROL = {24: "supervisor", 48: "director", 72: "administrador"}


def _emp(id_empresa=None):
    from src.services.gobierno import organigrama as _O
    return _O._emp(id_empresa)


def _registrar(emp, ref, desde, hacia, nivel, horas, motivo):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO org_escalados (id_empresa, referencia, desde_usuario, "
                        "hacia_usuario, nivel, horas, motivo) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, (ref or "")[:120], desde, hacia, nivel, horas, (motivo or "")[:255]))
            c.commit()
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("gobierno", "ESCALADO", "org_escalados", f"{ref} {desde}->{hacia} ({horas}h)")
        except Exception:
            pass
    except Exception as e:
        logger.error("registrar escalado: %s", e)


def revisar(id_empresa=None, umbrales=(24, 48, 72)) -> list:
    """Escala las ejecuciones/aprobaciones PENDIENTES que superan los umbrales de horas."""
    emp = _emp(id_empresa)
    escalados = []
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id, codigo_regla, usuario, TIMESTAMPDIFF(HOUR, creado, NOW()) horas "
                        "FROM automatizaciones_ejecuciones WHERE id_empresa=%s AND estado='PENDIENTE' "
                        "AND creado <= (NOW() - INTERVAL %s HOUR)", (emp, int(min(umbrales))))
            pendientes = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("revisar pendientes: %s", e)
        pendientes = []

    for p in pendientes:
        horas = int(p.get("horas") or 0)
        nivel_h = max([u for u in umbrales if horas >= u], default=umbrales[0])
        rol_destino = _NIVEL_ROL.get(nivel_h, "administrador")
        # Notifica al rol destino (reutiliza AutomationService/notificaciones).
        hacia = rol_destino
        try:
            from src.services.automatizacion import acciones as _AC
            _AC.crear_tarea({"n": 1, "prioridad": "ALTA"},
                            {"modulo": "workflow", "titulo": f"[Escalado {horas}h] Aprobacion pendiente"},
                            emp)
        except Exception:
            pass
        _registrar(emp, f"ejec:{p.get('id')}:{p.get('codigo_regla')}", p.get("usuario"),
                   hacia, list(umbrales).index(nivel_h) + 1, horas,
                   f"Pendiente {horas}h → escala a {rol_destino}")
        escalados.append({"referencia": p.get("codigo_regla"), "horas": horas, "hacia": hacia})
    return escalados


def registrar_job(id_empresa=None) -> bool:
    try:
        from src.services import scheduler
        scheduler.registrar("gobierno_escalado", lambda **_k: revisar(id_empresa))
        try:
            scheduler.registrar_job("gobierno_escalado", intervalo_horas=6,
                                    descripcion="Escalado automatico de aprobaciones", id_empresa=id_empresa)
        except Exception:
            pass
        return True
    except Exception:
        return False
