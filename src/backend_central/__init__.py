"""
Servidor CENTRAL de licencias (proyecto de infraestructura SaaS central — Fase 2, ver plan
`hazy-riding-aurora`). Aplicación Flask SEPARADA de `src/backend/app.py` (el backend que corre
como subproceso local de CADA instalación de escritorio): esta vive en infraestructura propia del
fundador (nunca en el equipo de un cliente) y habla contra su PROPIA base de datos central,
completamente distinta de la de cualquier cliente — nunca comparten servidor ni base de datos.

Reutiliza módulos ya existentes sin duplicarlos: `services.saas.suscripciones` (ciclo de vida de
la suscripción), `services.api_publica.developer/oauth` (credenciales M2U por instalación,
client-credentials), `db.empresa.crear_empresa` (alta de la empresa cliente EN LA BD CENTRAL — no
tiene relación con el `id_empresa` de la BD local del cliente). Arrancar:

    DB_HOST=... DB_NAME=smart_manager_central ... python -m src.backend_central.app
"""
