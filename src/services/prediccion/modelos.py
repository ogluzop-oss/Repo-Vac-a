"""
Ciclo de vida y versionado PERSISTENTE de modelos predictivos (Fase 6). Persiste los metadatos/métricas
REALES que calcula el motor de forecasting existente (no recalcula, no es un motor paralelo). Reutiliza la
auditoría (`log_auditoria`) y el Event Bus (`eventbus.publish`) existentes. Aislado por tenant (`id_empresa`).

Ciclo: TRAINING → VALIDATED → ACTIVE → DEPRECATED (o FAILED). Un modelo NO se activa si no está VALIDATED, y
solo sustituye al activo si MEJORA (menor MAE) o no hay activo. Toda activación/rechazo/degradación se audita
y emite evento. Nunca cruza datos entre tenants.
"""

import hashlib
import logging

from src.db.conexion import log_auditoria, obtener_conexion

logger = logging.getLogger("prediccion.modelos")

ESTADOS = ("TRAINING", "VALIDATED", "ACTIVE", "DEPRECATED", "FAILED")


def _hash(model_id, metricas, n_obs) -> str:
    sem = f"{model_id}|{metricas.get('mae')}|{metricas.get('rmse')}|{metricas.get('wape')}|{n_obs}"
    return hashlib.sha256(sem.encode()).hexdigest()


def registrar(model_id, *, id_empresa, entidad, algoritmo, tipo_modelo, n_observaciones=0,
              metricas=None, calidad_datos=None, entidad_id=None, estado="VALIDATED") -> dict:
    """Persiste un modelo con sus métricas reales. Estado inicial VALIDATED (ya backtesteado) o TRAINING."""
    metricas = metricas or {}
    if estado not in ESTADOS:
        estado = "VALIDATED"
    h = _hash(model_id, metricas, n_observaciones)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prediccion_modelos (model_id, id_empresa, entidad, entidad_id, algoritmo, "
                "tipo_modelo, n_observaciones, mae, rmse, wape, calidad_datos, estado, hash_integridad) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE estado=VALUES(estado)",
                (model_id, id_empresa, entidad, entidad_id, algoritmo, tipo_modelo, n_observaciones,
                 metricas.get("mae"), metricas.get("rmse"), metricas.get("wape"), calidad_datos, estado, h))
            conn.commit()
        log_auditoria("prediccion", "PRED_MODELO_REGISTRADO", "prediccion_modelos",
                      f"{model_id} {entidad} {algoritmo} estado={estado}")
        return {"ok": True, "model_id": model_id, "hash_integridad": h, "estado": estado}
    except Exception as e:
        logger.error("registrar: %s", e)
        return {"ok": False, "error": str(e)}


def obtener(model_id) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM prediccion_modelos WHERE model_id=%s", (model_id,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener: %s", e)
        return None


def obtener_activo(id_empresa, entidad, *, entidad_id=None) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM prediccion_modelos WHERE id_empresa<=>%s AND entidad=%s "
                        "AND entidad_id<=>%s AND estado='ACTIVE' ORDER BY fecha_activacion DESC LIMIT 1",
                        (id_empresa, entidad, entidad_id))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener_activo: %s", e)
        return None


def listar(id_empresa, *, entidad=None, limite=200) -> list:
    q = "SELECT * FROM prediccion_modelos WHERE id_empresa<=>%s"
    p = [id_empresa]
    if entidad:
        q += " AND entidad=%s"; p.append(entidad)
    q += " ORDER BY id DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def comparar(candidato: dict, activo: dict | None) -> dict:
    """Compara por MAE (menor es mejor); WAPE como desempate. Devuelve {mejor, criterio, mejora_pct}."""
    if not activo or activo.get("mae") is None:
        return {"mejor": "candidato", "criterio": "sin_modelo_activo", "mejora_pct": None}
    ca, aa = candidato.get("mae"), activo.get("mae")
    if ca is None:
        return {"mejor": "activo", "criterio": "candidato_sin_mae", "mejora_pct": None}
    ca, aa = float(ca), float(aa)
    if ca < aa:
        mejora = round((aa - ca) / aa * 100, 2) if aa else None
        return {"mejor": "candidato", "criterio": "menor_mae", "mejora_pct": mejora}
    return {"mejor": "activo", "criterio": "no_mejora", "mejora_pct": None}


def activar(model_id, *, id_empresa, usuario=None) -> dict:
    """Activa un modelo SOLO si está VALIDATED y mejora (o no hay activo). Deprecia el anterior. Auditado."""
    m = obtener(model_id)
    if not m or str(m.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "error": "modelo inexistente o de otro tenant"}   # aislamiento
    if m.get("estado") not in ("VALIDATED", "ACTIVE"):
        return {"ok": False, "error": f"no activable en estado {m.get('estado')} (requiere VALIDATED)"}
    activo = obtener_activo(id_empresa, m["entidad"], entidad_id=m.get("entidad_id"))
    cmp = comparar(m, activo)
    if cmp["mejor"] != "candidato":
        log_auditoria("prediccion", "PRED_MODELO_RECHAZADO", "prediccion_modelos",
                      f"{model_id} no mejora al activo ({cmp['criterio']})")
        return {"ok": False, "activado": False, "motivo": cmp["criterio"], "comparacion": cmp}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if activo:
                cur.execute("UPDATE prediccion_modelos SET estado='DEPRECATED', fecha_desactivacion=NOW() "
                            "WHERE model_id=%s", (activo["model_id"],))
            cur.execute("UPDATE prediccion_modelos SET estado='ACTIVE', fecha_activacion=NOW() "
                        "WHERE model_id=%s", (model_id,))
            conn.commit()
        log_auditoria("prediccion", "PRED_MODELO_ACTIVADO", "prediccion_modelos",
                      f"{model_id} {m['entidad']} (mejora={cmp.get('mejora_pct')}%) por {usuario}")
        _evento("prediccion.modelo_activado", id_empresa, m, extra={"mejora_pct": cmp.get("mejora_pct")})
        return {"ok": True, "activado": True, "comparacion": cmp}
    except Exception as e:
        logger.error("activar: %s", e)
        return {"ok": False, "error": str(e)}


def rechazar(model_id, *, id_empresa, motivo="rechazado", usuario=None) -> dict:
    m = obtener(model_id)
    if not m or str(m.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "error": "modelo inexistente o de otro tenant"}
    _set_estado(model_id, "FAILED")
    log_auditoria("prediccion", "PRED_MODELO_RECHAZADO", "prediccion_modelos", f"{model_id} {motivo} por {usuario}")
    return {"ok": True, "estado": "FAILED"}


def desactivar(model_id, *, id_empresa, usuario=None) -> dict:
    m = obtener(model_id)
    if not m or str(m.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "error": "modelo inexistente o de otro tenant"}
    _set_estado(model_id, "DEPRECATED", desactivar=True)
    log_auditoria("prediccion", "PRED_MODELO_DESACTIVADO", "prediccion_modelos", f"{model_id} por {usuario}")
    return {"ok": True, "estado": "DEPRECATED"}


def evaluar_degradacion(id_empresa, entidad, wape_actual, *, entidad_id=None, umbral=1.5) -> dict:
    """Compara el WAPE reciente con el del modelo activo. Si empeora > `umbral`× → degradación + evento.
    Estados: MODEL_HEALTHY / MODEL_WARNING / MODEL_DEGRADED / MODEL_RETRAIN_REQUIRED."""
    activo = obtener_activo(id_empresa, entidad, entidad_id=entidad_id)
    if not activo or activo.get("wape") is None or wape_actual is None:
        return {"estado": "MODEL_HEALTHY", "motivo": "sin base de comparación"}
    base = float(activo["wape"]) or 1e-9
    ratio = float(wape_actual) / base
    if ratio <= 1.15:
        estado = "MODEL_HEALTHY"
    elif ratio <= umbral:
        estado = "MODEL_WARNING"
    elif ratio <= umbral * 1.5:
        estado = "MODEL_DEGRADED"
    else:
        estado = "MODEL_RETRAIN_REQUIRED"
    if estado in ("MODEL_DEGRADED", "MODEL_RETRAIN_REQUIRED"):
        _evento("prediccion.modelo_degradado", id_empresa, activo,
                extra={"wape_actual": wape_actual, "wape_base": activo["wape"], "estado": estado})
        if estado == "MODEL_RETRAIN_REQUIRED":
            _evento("prediccion.reentrenamiento_requerido", id_empresa, activo, extra={"ratio": round(ratio, 3)})
        log_auditoria("prediccion", "PRED_MODELO_DEGRADADO", "prediccion_modelos",
                      f"{activo['model_id']} {entidad} {estado} (wape {activo['wape']}→{wape_actual})")
    return {"estado": estado, "ratio": round(ratio, 3), "model_id": activo["model_id"]}


# ── internos ──────────────────────────────────────────────────────────────────
def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _set_estado(model_id, estado, *, desactivar=False):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if desactivar:
                cur.execute("UPDATE prediccion_modelos SET estado=%s, fecha_desactivacion=NOW() "
                            "WHERE model_id=%s", (estado, model_id))
            else:
                cur.execute("UPDATE prediccion_modelos SET estado=%s WHERE model_id=%s", (estado, model_id))
            conn.commit()
    except Exception as e:
        logger.error("_set_estado: %s", e)


def _evento(tipo, id_empresa, modelo, *, extra=None):
    try:
        from src.services.eventbus import publish
        payload = {"model_id": modelo.get("model_id"), "entidad": modelo.get("entidad"),
                   "algoritmo": modelo.get("algoritmo"), "tipo_modelo": modelo.get("tipo_modelo")}
        payload.update(extra or {})
        publish(tipo, id_empresa=id_empresa, payload=payload)
    except Exception as e:
        logger.debug("evento %s: %s", tipo, e)
