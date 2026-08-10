"""
Communication Governance (CCP Fase II · B10) — gobierno de las comunicaciones.

RGPD/consentimientos, políticas (listas negras/blancas, canales permitidos/prohibidos, retención),
prioridades y restricciones legales. Se aplica como POLÍTICA del pipeline del Corporate Communication
Service (`evaluar` decide si una comunicación puede salir) y toda decisión queda asociada al
Communication ID. Reutiliza RBAC/auditoría. Multiempresa. API-First (sin PyQt).
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.gobierno")

TIPOS_POLITICA = ("lista_negra", "lista_blanca", "canal_prohibido", "canal_permitido", "retencion")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or "") or None
    except Exception:
        return None


# ── Consentimientos (RGPD) ────────────────────────────────────────────────────
def registrar_consentimiento(correo, *, id_empresa=None, canal="email", estado="otorgado",
                             base_legal=None, usuario=None) -> bool:
    id_empresa = _emp(id_empresa)
    correo = (correo or "").strip().lower()
    if not correo:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ccp_consentimientos (id_empresa, correo, canal, estado, base_legal, "
                "usuario) VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE estado=VALUES(estado), "
                "base_legal=VALUES(base_legal), usuario=VALUES(usuario), fecha=NOW()",
                (id_empresa, correo, canal, estado, base_legal, _usuario(usuario)))
            conn.commit()
            return True
    except Exception as e:
        logger.error("registrar_consentimiento: %s", e)
        return False


def consentimiento(correo, *, id_empresa=None, canal="email") -> str:
    """Estado del consentimiento ('otorgado'/'revocado'/'sin_registro'). Sin registro = permitido por
    defecto (compatibilidad); una política de opt-in estricto puede cambiarlo."""
    id_empresa = _emp(id_empresa)
    correo = (correo or "").strip().lower()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado FROM ccp_consentimientos WHERE id_empresa=%s AND correo=%s "
                        "AND canal=%s", (id_empresa, correo, canal))
            r = cur.fetchone()
            if r:
                return r[0] if not isinstance(r, dict) else r.get("estado")
    except Exception as e:
        logger.debug("consentimiento: %s", e)
    return "sin_registro"


# ── Políticas ─────────────────────────────────────────────────────────────────
def anadir_politica(tipo, valor=None, *, id_empresa=None, canal=None, observaciones=None,
                    usuario=None) -> int | None:
    if tipo not in TIPOS_POLITICA:
        return None
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ccp_politicas_comunicacion (id_empresa, tipo, valor, canal, "
                        "activo, observaciones, usuario) VALUES (%s,%s,%s,%s,1,%s,%s)",
                        (id_empresa, tipo, (valor or "").strip().lower() or None, canal,
                         observaciones, _usuario(usuario)))
            pid = cur.lastrowid
            conn.commit()
            return pid
    except Exception as e:
        logger.error("anadir_politica: %s", e)
        return None


def listar_politicas(id_empresa=None, *, tipo=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM ccp_politicas_comunicacion WHERE id_empresa=%s AND activo=1"
    p = [id_empresa]
    if tipo:
        q += " AND tipo=%s"; p.append(tipo)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_politicas: %s", e)
        return []


# ── Evaluación (pipeline del Communication Service) ───────────────────────────
def evaluar(id_empresa, correo, canal) -> tuple:
    """Decide si una comunicación puede salir. Devuelve (permitido: bool, motivo: str). Multiempresa."""
    id_empresa = _emp(id_empresa)
    correo = (correo or "").strip().lower()
    pols = listar_politicas(id_empresa)
    negras = {p["valor"] for p in pols if p["tipo"] == "lista_negra" and p.get("valor")}
    blancas = {p["valor"] for p in pols if p["tipo"] == "lista_blanca" and p.get("valor")}
    canales_prohibidos = {p["canal"] for p in pols if p["tipo"] == "canal_prohibido" and p.get("canal")}
    if correo in negras:
        return False, "destinatario en lista negra"
    if blancas and correo not in blancas:
        return False, "lista blanca activa: destinatario no autorizado"
    if canal in canales_prohibidos:
        return False, f"canal '{canal}' prohibido por política"
    if consentimiento(correo, id_empresa=id_empresa, canal=canal) == "revocado":
        return False, "consentimiento revocado (RGPD)"
    return True, "ok"
