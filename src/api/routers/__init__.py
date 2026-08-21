"""
Routers de la Enterprise REST API (Fase III · B2). Cada módulo expone `registrar(bp)` que añade sus
rutas al blueprint. Añadir un recurso nuevo = un router más en esta lista (los ~19 grupos del catálogo
se cablean con una línea por recurso sobre esta misma arquitectura)."""

from src.api.routers import (auth, system, communications, templates, campaigns, contacts, audit,
                             recordings, commerce, webauthn, realtime, portal)

# NOTA: los routers portal_proveedor y lonja_vendedor se retiraron (desmontaje del portal externo
# + lonja, refactorización del módulo Proveedores, Fase 1). `portal` = storefront/back-office (WEB-04).
ROUTERS = [auth, system, communications, templates, campaigns, contacts, audit, recordings,
           commerce, webauthn, realtime, portal]


def registrar_todos(bp):
    for r in ROUTERS:
        r.registrar(bp)
