"""
Portal Web para Empleados · Interfaz de secciones (Fase WEB-09).

Paquete de UI del Back Office web: componentes reutilizables (`componentes`) + una sección por área
(`inicio`, `buscador_global`). Cada sección es una VISTA DELGADA que solo PRESENTA información consumiendo
`services/*` / `db/*` existentes — sin lógica de negocio propia, sin duplicar servicios/reglas (N7).
Multiempresa/multitienda y RBAC se resuelven en los servicios (contexto del token/sesión), no aquí. Todo es
DEGRADABLE: si un servicio o dato no está disponible, la vista muestra un estado vacío en vez de fallar.

La sección "Pedidos online" reutiliza directamente `gui/portal_web_home.PortalWebHome` (núcleo extraído en
WEB-08). Las secciones de Reservas/Encargos/Stock/Logística/Clientes/Configuración se retiraron por
duplicar módulos propios del ERP (Logística/CRM/Mostrar Stock/Canal Web).
"""
