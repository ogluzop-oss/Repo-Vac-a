"""
Politicas de distribucion por tipo de evento (Fase 2, SUBFASE 2.9 + 2.3).

Cada evento define: si requiere sincronizacion inmediata (CRITICA) o puede esperar a la
ventana (PROGRAMADA), su ambito (scope) de destinatarios, y flags (requiere confirmacion/
aprobacion, solo lectura, solo central/tienda/almacen). Extensible: los tipos no listados
usan la politica por defecto.
"""

from src.services.eventos import prioridades as _P

# scope: EMPRESA | GRUPO | TIENDA | CENTRAL | ALMACEN
DEFECTO = {
    "sincronizacion": "PROGRAMADA",
    "scope": "EMPRESA",
    "requiere_confirmacion": True,
    "requiere_aprobacion": False,
    "solo_lectura": False,
}

# Tipos que SIEMPRE son criticos (sincronizacion inmediata).
CRITICOS = {
    "PRECIO_ACTUALIZADO", "ARTICULO_ELIMINADO", "PROMOCION_PUBLICADA", "PROMOCION_FINALIZADA",
    "USUARIO_BLOQUEADO", "ROL_MODIFICADO", "LICENCIA_SUSPENDIDA", "ERROR_CRITICO",
}

# Overrides por tipo (se fusionan sobre DEFECTO).
OVERRIDES = {
    # ── Criticos (a toda la empresa, inmediato) ──
    "PRECIO_ACTUALIZADO":   {"sincronizacion": "CRITICA", "scope": "EMPRESA"},
    "ARTICULO_ELIMINADO":   {"sincronizacion": "CRITICA", "scope": "EMPRESA"},
    "PROMOCION_PUBLICADA":  {"sincronizacion": "CRITICA", "scope": "EMPRESA"},
    "PROMOCION_FINALIZADA": {"sincronizacion": "CRITICA", "scope": "EMPRESA"},
    "USUARIO_BLOQUEADO":    {"sincronizacion": "CRITICA", "scope": "EMPRESA"},
    "ROL_MODIFICADO":       {"sincronizacion": "CRITICA", "scope": "EMPRESA"},
    "LICENCIA_SUSPENDIDA":  {"sincronizacion": "CRITICA", "scope": "EMPRESA"},
    # ── Consolidacion en central (programado) ──
    "DOCUMENTO_PUBLICADO":  {"scope": "CENTRAL"},
    "FACTURA_GENERADA":     {"scope": "CENTRAL", "requiere_confirmacion": True},
    "FACTURA_ANULADA":      {"scope": "CENTRAL"},
    "FACTURA_RECTIFICADA":  {"scope": "CENTRAL"},
    "COBRO_REGISTRADO":     {"scope": "CENTRAL"},
    "KARDEX_MOVIMIENTO":    {"scope": "CENTRAL"},
    "MERMA_REGISTRADA":     {"scope": "CENTRAL"},
    "NOMINA_GENERADA":      {"scope": "CENTRAL"},
    "REPOSICION_GENERADA":  {"scope": "CENTRAL"},
    "INVENTARIO_CORREGIDO": {"scope": "CENTRAL"},
    "PEDIDO_RECIBIDO":      {"scope": "CENTRAL"},
    # ── Maestros que se propagan a toda la empresa ──
    "ARTICULO_CREADO":      {"scope": "EMPRESA"},
    "ARTICULO_MODIFICADO":  {"scope": "EMPRESA"},
    "CLIENTE_CREADO":       {"scope": "EMPRESA"},
    "CLIENTE_MODIFICADO":   {"scope": "EMPRESA"},
    "PROVEEDOR_ACTUALIZADO": {"scope": "EMPRESA"},
    # ── Integracion Fase 2 (consolidacion en central) ──
    "VENTA_REGISTRADA":     {"scope": "CENTRAL"},
    "ASIENTO_CONTABILIZADO": {"scope": "CENTRAL"},
    "BI_SNAPSHOT_GENERADO": {"scope": "CENTRAL", "requiere_confirmacion": False},
    "UBICACION_ASIGNADA":   {"scope": "TIENDA"},
    "WORKFLOW_INICIADO":    {"scope": "EMPRESA"},
}


def politica(tipo, prioridad=None) -> dict:
    """Politica efectiva para un tipo de evento (DEFECTO + override + regla de criticidad)."""
    pol = dict(DEFECTO)
    pol.update(OVERRIDES.get(str(tipo), {}))
    if (str(prioridad or "").upper() == _P.CRITICA) or (str(tipo) in CRITICOS):
        pol["sincronizacion"] = "CRITICA"
    return pol


def es_critica(tipo, prioridad=None) -> bool:
    return politica(tipo, prioridad)["sincronizacion"] == "CRITICA"


# ── SUBFASE 4.10 · Politicas de tiempo de sincronizacion por prioridad ────────
# Gobernado por reglas (no hardcode disperso): intervalo objetivo en segundos. None = ventana
# de mantenimiento (03:00). Configurable por empresa (distribucion_config.reintentos... o override).
INTERVALOS_SYNC = {
    "CRITICA": 0,        # tiempo real
    "ALTA": 60,          # < 1 minuto
    "MEDIA": 300,        # cada 5 minutos
    "BAJA": None,        # ventana de mantenimiento (03:00)
    "INFORMATIVA": None,
}


def intervalo_sync(prioridad, id_empresa=None) -> int | None:
    """Segundos objetivo de sincronizacion para una prioridad (None = ventana de mantenimiento).
    Admite override por empresa (regla, no hardcode)."""
    p = str(prioridad or "MEDIA").upper()
    base = INTERVALOS_SYNC.get(p, 300)
    try:
        from src.services.distribucion import config as _cfg
        ov = (_cfg.obtener(id_empresa) or {}).get(f"sync_{p.lower()}_seg")
        if ov is not None:
            return int(ov)
    except Exception:
        pass
    return base
