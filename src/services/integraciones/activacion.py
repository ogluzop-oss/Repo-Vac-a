"""
Activación de integraciones de PRODUCCIÓN (readiness) — R2/R3/R4.

Algunas integraciones aportan valor solo con credenciales/infra EXTERNAS de pago (pasarelas de pago,
agregador bancario PSD2, certificado + alta AEAT). Su MOTOR ya existe en el repo y es DEGRADABLE a
'simulado' (N7 — no se crea nada nuevo aquí). Este módulo NO cobra, NO conecta ni activa nada: solo LEE
el estado actual (best-effort) y reporta, por integración, si está en modo 'simulado'/'preparado' o ya
'live', y QUÉ falta para activarla en producción.

Es la "estructura lista para producción": la base para encender cada integración cuando se disponga de las
credenciales, sin fabricar datos ni simular un 'activado' que no es real (honestidad).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("integraciones.activacion")

# Proveedores de pasarela de pago reconocidos (el motor es provider-agnostic; esto es solo para detectar
# si hay una conexión REAL configurada frente a 'simulado').
_PROV_PAGO = ("stripe", "paypal", "redsys")

# Catálogo declarativo de las integraciones que requieren activación externa (coste de producción).
# `modo`/`listo` se resuelven en tiempo real con los detectores best-effort de abajo.
_CATALOGO = [
    {"clave": "pagos", "requisito": "R2",
     "nombre": "Pasarela de pago (Stripe/PayPal/Redsys)",
     "motor": "src/services/comercio_digital/pagos",
     "requiere": ["Alta en la pasarela (cuenta de comercio)",
                  "Claves de API de PRODUCCIÓN en la conexión (cifradas)",
                  "Webhook firmado (HMAC) apuntando al endpoint de pagos"]},
    {"clave": "banca_psd2", "requisito": "R3",
     "nombre": "Conexión bancaria PSD2 (open banking)",
     "motor": "src/services/banca_online",
     "requiere": ["Contrato con un agregador PSD2 (TPP)",
                  "Credenciales de PRODUCCIÓN de la conexión (cifradas)",
                  "Consentimiento de cuentas y desactivar modo_simulado"]},
    {"clave": "aeat", "requisito": "R4",
     "nombre": "Verifactu / factura-e (AEAT)",
     "motor": "src/services/fiscal",
     "requiere": ["Certificado PKCS#12 de PRODUCCIÓN importado y activo",
                  "Alta del obligado tributario en la AEAT",
                  "mTLS operativo contra los endpoints oficiales"]},
]

_DETECTORES = {}


def _detector(clave):
    def _reg(fn):
        _DETECTORES[clave] = fn
        return fn
    return _reg


@_detector("pagos")
def _modo_pagos(emp) -> bool:
    """True (live) si hay una conexión de pasarela de pago REAL configurada (no 'simulado')."""
    try:
        from src.services.comercio_digital import conexiones
        for c in (conexiones.listar(id_empresa=emp) or []):
            prov = str(c.get("proveedor") or "").lower()
            if prov in _PROV_PAGO:
                return True
    except Exception as e:
        logger.debug("_modo_pagos: %s", e)
    return False


@_detector("banca_psd2")
def _modo_banca(emp) -> bool:
    """True (live) si existe alguna conexión bancaria con modo_simulado=0."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM banca_conexiones WHERE id_empresa=%s AND modo_simulado=0",
                        (emp,))
            r = cur.fetchone()
            return int((list(r.values())[0] if isinstance(r, dict) else r[0]) or 0) > 0
    except Exception as e:
        logger.debug("_modo_banca: %s", e)
    return False


@_detector("aeat")
def _modo_aeat(emp) -> bool:
    """True (live) si hay un certificado fiscal activo importado (la transmisión real la fija el worker
    con el acuse de la AEAT; aquí solo se detecta que el material de producción está presente)."""
    try:
        from src.services.fiscal import certificados
        return certificados.obtener_activo(emp) is not None
    except Exception as e:
        logger.debug("_modo_aeat: %s", e)
    return False


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def estado_activacion(id_empresa=None) -> list:
    """Estado de activación de cada integración de producción. Cada entrada:
    {clave, requisito, nombre, motor, modo:'live'|'simulado', listo:bool, requiere:[...]}.
    'simulado' = motor operativo en modo degradable (base lista, sin credenciales reales)."""
    emp = _emp(id_empresa)
    salida = []
    for item in _CATALOGO:
        detector = _DETECTORES.get(item["clave"])
        live = False
        try:
            live = bool(detector(emp)) if detector else False
        except Exception as e:
            logger.debug("detector %s: %s", item["clave"], e)
        salida.append({**item, "modo": "live" if live else "simulado", "listo": live})
    return salida


def resumen(id_empresa=None) -> dict:
    """Resumen de una ojeada: cuántas integraciones están en producción vs preparadas (simulado)."""
    est = estado_activacion(id_empresa)
    en_produccion = [e["clave"] for e in est if e["listo"]]
    preparadas = [e["clave"] for e in est if not e["listo"]]
    return {"total": len(est), "en_produccion": en_produccion, "preparadas": preparadas,
            "todo_en_produccion": len(preparadas) == 0, "detalle": est}


__all__ = ["estado_activacion", "resumen"]
