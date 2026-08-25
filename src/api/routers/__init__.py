"""
Routers de la Enterprise REST API (Fase III · B2). Cada módulo expone `registrar(bp)` que añade sus
rutas al blueprint. Añadir un recurso nuevo = un router más en esta lista (los ~19 grupos del catálogo
se cablean con una línea por recurso sobre esta misma arquitectura)."""

from src.api.routers import (auth, system, communications, templates, campaigns, contacts, audit,
                             recordings, commerce, webauthn, realtime, portal, customers, suppliers,
                             orders, stock, notifications, agenda, tasks)

# NOTA: los routers portal_proveedor y lonja_vendedor se retiraron (desmontaje del portal externo
# + lonja, refactorización del módulo Proveedores, Fase 1). `portal` = storefront/back-office (WEB-04).
# customers/suppliers/orders/stock (cierre de brecha catálogo móvil, ver mobile_client/README.md):
# solo lectura, apoyados en los módulos ya existentes de src/db/ vía una capa fina en src/services/.
# notifications/agenda: consumen directamente src/services/notificaciones.py y calendario.py, que ya
# eran la capa de servicio real (no hacía falta una capa fina adicional).
ROUTERS = [auth, system, communications, templates, campaigns, contacts, audit, recordings,
           commerce, webauthn, realtime, portal, customers, suppliers, orders, stock,
           notifications, agenda, tasks]


def registrar_todos(bp):
    for r in ROUTERS:
        r.registrar(bp)
