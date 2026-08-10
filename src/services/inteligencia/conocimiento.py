"""
Etapa C · Fase C6 — Conocimiento Empresarial (Área 7).

Capa de conocimiento corporativo que BUSCA y RESPONDE sobre la documentación YA existente (Centro
Documental: contratos/facturas/pedidos/auditorías/legal/incidencias/procedimientos/manuales/histórico)
reutilizando `db.documentos`. Responde EXCLUSIVAMENTE con información AUTORIZADA según RBAC (filtra por
el permiso requerido de cada tipo de documento) y SIEMPRE con referencias verificables; NUNCA inventa.
Solo lectura, multiempresa, degradable. No crea tablas ni motores nuevos.
"""

from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger("inteligencia.conocimiento")


def _norm(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()

FASE = "C6"

# Permiso RBAC requerido por tipo de documento (defecto: documentos.ver).
_PERMISO_TIPO = {"contrato": "rrhh.ver", "factura": "contabilidad.ver",
                 "factura_rect": "contabilidad.ver", "pedido": "ventas.ver",
                 "grabacion": "seguridad.acl", "nomina": "rrhh.ver"}
_DEFECTO = "documentos.ver"


def _emp(id_empresa=None):
    from src.services import inteligencia
    return inteligencia._emp(id_empresa)


def _puede(usuario, permiso, emp):
    from src.services import inteligencia
    return inteligencia._puede(usuario, permiso, emp)


def _permiso_de(tipo):
    return _PERMISO_TIPO.get(tipo, _DEFECTO)


def buscar(consulta=None, *, id_empresa=None, usuario=None, tipo=None, limite=20):
    """Busca documentos autorizados (RBAC por tipo) que coincidan con la consulta. Devuelve REFERENCIAS
    verificables (no el contenido). Requiere `inteligencia.ver` + el permiso del tipo de documento."""
    emp = _emp(id_empresa)
    if not _puede(usuario, "inteligencia.ver", emp):
        return []
    if tipo and not _puede(usuario, _permiso_de(tipo), emp):
        return []       # no autorizado para ese tipo
    try:
        from src.db import documentos
        docs = documentos.listar_documentos(tipo=tipo, id_empresa=emp, limite=limite * 20)
    except Exception as e:
        logger.error("buscar(%s): %s", consulta, e)
        return []
    # Palabras clave de la consulta (tokens alfanuméricos ≥4) para casar por nombre/referencia.
    import re
    palabras = re.findall(r"[a-z0-9]{4,}", _norm(consulta)) if consulta else []
    out = []
    for d in docs:
        t = d.get("tipo_documento") or d.get("tipo") or "otros"
        if not _puede(usuario, _permiso_de(t), emp):
            continue                      # filtro RBAC por tipo de documento
        if palabras:
            texto = _norm(d.get("nombre")) + " " + _norm(d.get("referencia"))
            if not any(w in texto for w in palabras):
                continue                  # no coincide con ninguna palabra clave
        out.append({"id": d.get("id") or d.get("id_documento"), "tipo": t,
                    "nombre": d.get("nombre"), "referencia": d.get("referencia"),
                    "fecha": str(d.get("fecha_generacion") or d.get("fecha") or ""),
                    "cliente": d.get("cliente")})
        if len(out) >= limite:
            break
    return out


def responder(pregunta, *, id_empresa=None, usuario=None):
    """Responde una pregunta apoyándose SOLO en documentos autorizados. Si no hay documentación
    autorizada, lo indica (NUNCA inventa). La respuesta cita los documentos (verificable)."""
    emp = _emp(id_empresa)
    docs = buscar(pregunta, id_empresa=emp, usuario=usuario, limite=10)
    if not docs:
        return {"texto": "No dispongo de documentación autorizada para responder eso.",
                "documentos": [], "verificable": False}
    tipos = sorted({d["tipo"] for d in docs})
    return {"texto": f"Encontré {len(docs)} documento(s) autorizado(s) relacionados "
                     f"({', '.join(tipos)}). Puedes consultarlos para el detalle.",
            "documentos": docs, "verificable": True}


def descriptor() -> dict:
    return {"servicio": "inteligencia.conocimiento", "etapa": "C", "fase": FASE,
            "estado": "implementado", "reutiliza": ["db.documentos (Centro Documental)", "rbac"],
            "permiso_por_tipo": dict(_PERMISO_TIPO), "solo_lectura": True, "inventa": False,
            "modifica_datos": False, "motor_nuevo": False, "rbac_por_tipo": True}


__all__ = ["FASE", "buscar", "responder", "descriptor"]
