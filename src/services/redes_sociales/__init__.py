"""
Gestión de Redes Sociales Corporativas (petición explícita, módulo nuevo completo, migr. 0325):
cuentas conectadas (OAuth), bandeja de entrada omnicanal (Social CRM), calendario de contenidos,
analítica cruzada con el ERP y monitorización de reputación con escalado automático a
`services.incidencias_internas`. Acceso EXCLUSIVO de SUPERADMIN (RBAC en la GUI, igual criterio que
`services/camaras`/`services/transporte`).

Auditoría previa (ver migración 0325): no existía ninguna pieza de este dominio en el repo — la
única integración social preexistente es TikTok Shop (catálogo/pedidos, sin relación con
mensajería/reputación). Todo este paquete reutiliza, sin duplicar: `utils.cripto`/
`secret_manager` (cifrado de tokens OAuth), `db.documentos` (adjuntos), `services.eventos` (bus),
`services.incidencias_internas.tickets` (escalado), y la taxonomía de errores de integración ya
existente en `services.marketplace.integraciones_comerciales.motor.errores`.
"""
