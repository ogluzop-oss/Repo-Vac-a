# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Smart Manager is a Windows desktop application built with PyQt6 for warehouse/retail inventory management. It covers pallet reception, store-location mapping, stock tracking, POS/sales, price labels, loss tracking (mermas), and AI-driven demand forecasting.

## Running the Application

```bash
python src/main.py
```

Requires MariaDB running and a `.env` file in the project root (or environment variables set):

```
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=admin123
DB_NAME=smart_manager_db
DB_PORT=3306
```

Database tables are auto-initialized from `src/database/bootstrap_mariadb.sql` on first run.

## Key Dependencies

```
PyQt6, pymysql, pandas, prophet, matplotlib, reportlab, Pillow,
openpyxl, python-barcode, opencv-python, requests, python-dotenv
```

No `requirements.txt` exists yet — infer versions from import usage. There are no automated tests or linting configuration.

## Architecture

```
src/main.py               Entry point — SmartManagerApp (QStackedWidget)
src/gui/                  All UI screens (login, menus, feature windows)
src/db/                   Database layer (conexion.py + per-domain modules)
src/utils/                Shared utilities (RFID, printing, API client, etc.)
src/database/             SQL bootstrap and seed scripts
assets/                   Global stylesheet (estilo_global.py), fonts, logo
documentos/               Runtime output directory (PDFs, labels, reports)
```

### Application Lifecycle

1. `SmartManagerApp.__init__` starts a Flask backend subprocess (planned: `src/backend/app.py`), initializes the DB connection pool, and shows `LoginWindow`.
2. On login, a `SesionUsuario` singleton holds the active user (role: `ADMINISTRADOR`, `GERENTE`, or `OPERARIO`). Role gates which menu cards are visible.
3. `MenuPrincipal` renders `MenuCardButton` widgets; each routes to a feature module pushed onto the `QStackedWidget`.
4. A `RFIDWorker` (QThread) runs continuously, polling `LectorZebraGateway` (Zebra FX/RFD HTTP API). It emits signals consumed by the reception and location screens.

### Database Layer (`src/db/`)

- `conexion.py` — connection pool (`get_connection()`), DB auto-initialization, SSL support.
- Per-domain modules: `articulos.py`, `logistica.py`, `pedidos.py`, `etiquetas.py`, `mermas.py`, `operaciones.py`, `usuario.py`.
- Direct pymysql queries; no ORM.

### GUI Pattern

- All screens inherit from `QWidget` or `QDialog`.
- Thread-safe UI updates use PyQt6 signals/slots — never call Qt widgets directly from worker threads.
- Global styling lives in `assets/estilo_global.py` (dark mode, cyan accent `#00FFC6`).

### UI / Enterprise Shell — REGLAS DE ARQUITECTURA (OBLIGATORIAS)

La UI Enterprise se organiza en dos capas con dependencia estricta
`foundation → components → panels → windows` (Foundation NUNCA depende de Components):

- `src/gui/foundation/` — primitivas: `tokens.py` (colores semánticos INFO/ANALISIS/ADVERTENCIA/
  CRITICO/OK), `icons.py` (un icono por concepto), `permissions.py` (permisos visuales
  visible/oculto/solo_lectura/editable por RBAC+Gobierno+empresa/tienda), `export.py`
  (`exportar_excel` único), `events.py` (Event Registry: solo eventos de UI), `shell.py`
  (`BaseEnterpriseWindow/Panel` framework-agnósticos + `QtEnterpriseWindow/QtEnterprisePanel`).
- `src/gui/components/` — librería visual única: `EnterpriseTable/Card/Toolbar/Search/Filter/
  DashboardGrid/Timeline/StatusBadge/RiskIndicator`.

Reglas permanentes (aplican a TODO desarrollo futuro, incluido dentro de meses):

1. **Enterprise Shell + librería obligatorios**: toda pantalla nueva se construye con
   `QtEnterpriseWindow`/`QtEnterprisePanel` y los widgets de `gui/components/`. Prohibido crear
   tablas, tarjetas, buscadores, filtros, toolbars, badges o indicadores fuera de la librería, salvo
   justificación técnica documentada.
2. **No lógica de negocio en la GUI**: las ventanas/paneles solo orquestan interfaz; toda la lógica
   vive en `services/` (y a futuro `domain/`/`repositories/`).
3. **Deprecación**: al sustituir una pantalla no se elimina de inmediato — marcar `@deprecated`,
   mantener un ciclo y eliminar solo cuando no queden referencias (imports/rutas/callbacks).
4. **Migración incremental (Strangler Pattern)**: prohibido reescribir módulos completos; sustitución
   progresiva creando infraestructura nueva y migrando gradualmente lo existente.

Otras invariantes: pestañas con **lazy loading** (init en primer acceso, vía factory en el shell);
Event Registry solo publica eventos de UI (`PanelOpened/Closed/DataLoaded/ActionExecuted/
RefreshRequested/PermissionChanged`), nunca eventos de dominio; conservar `v_id`/rutas/firmas
públicas al sustituir ventanas (compatibilidad hacia atrás). El hub BI es el **Centro de Inteligencia
Empresarial** (`inteligencia_gui.py`, v_id "bi"): Dashboard Ejecutivo · Centro de Actividad · Gemelo ·
Predicción · Simulador. Gobierno vive en Seguridad; Automatización/Autonomía/Historial en Aprobaciones.

### Comercio Digital — RESPONSABILIDADES CONGELADAS (rearquitectura, certificada)

Reorganización del área de Comercio Digital (Catálogo · Canal Web · Marketplace). Responsabilidades
oficiales y permanentes (aplican a TODO desarrollo futuro):

- **Catálogo** (`gui/catalogo_gestion.py`, `db/catalogo.py`, `services/catalogo/`) = **PIM**: SOLO
  producto (productos/categorías/marcas/etiquetas/variantes/atributos/fotos/relaciones/reservas). NO
  gestiona infraestructura (dominios/DNS/HTTPS/hosting/generación/publicación/sync/pasarelas). La antigua
  pestaña "Web" es solo un **punto de redirección** a Canal Web (`_abrir_canal_web`).
- **Canal Web** (`services/comercio_digital/canal_web/`, UI en `gui/tpv.py::_CanalWebConfigDialog`) =
  ÚNICO centro de la **presencia digital**: generación Fable 5, publicación, dominios, y la **marca**
  (nombre/logo/color/moneda/activa). **Fuente ÚNICA de marca/activación = `web_config`** (vía `db/web_tienda.py`,
  reutilizada — N7), que es lo que sirve `backend/storefront.py`. Canal Web es el **único editor** de
  `web_config`; `crear/actualizar_config/publicar/despublicar` la mantienen sincronizada (`_sync_web_config`).
  `cd_canal_web.config_negocio` es metadato operativo, NO fuente de marca. Canal Web NO edita datos maestros.
- **Marketplace** (`services/marketplace/`, `gui/marketplace_gui.py`) = **App Store de Plugins y
  Extensiones** (reutiliza el Plugin SDK). NO es canal de venta ni gestiona negocio (solo instala/administra;
  la EJECUCIÓN de cada conector vive en su módulo consumidor, p. ej. Canal Web).
- `ecommerce_config` (`db/ecommerce.py`) = **Escenario A** (conexión a plataforma EXTERNA:
  WooCommerce/Shopify/Prestashop) — responsabilidad DISTINTA de la web propia (Escenario B/`web_config`),
  NO una duplicidad. Sigue en uso (`services/tpv/ecommerce/*`, `catalog_sync_service`).
- Tres módulos llamados `catalogo` con dominios distintos (NO duplicidad): `db.catalogo` (PIM),
  `comercio_digital.catalogo` (ficha comercial compuesta), `marketplace.catalogo` (plugins).

### MFA / Autenticación multifactor (arquitectura CONGELADA, certificada)

Sistema MFA empresarial construido SOBRE la infraestructura existente (N7 — sin motores paralelos). El
**motor TOTP único** vive en `src/services/seguridad/mfa.py` (RFC 6238 propio, secreto cifrado Fernet
vía `utils/cripto`, recovery codes hasheados; tablas `mfa_usuarios`/`mfa_recovery_codes`, migr 0060).
Todo lo demás lo ORQUESTA (no lo duplica):

- **Gobernanza (`mfa_politica.py`, migr 0160)**: política por EMPRESA (`opcional`/`obligatorio`, métodos,
  `roles_obligatorios`). `politica_efectiva(usuario, rol, id_empresa, contexto)` resuelve en orden
  **empresa → override rol → contexto**, con suelo `ROLES_CRITICOS` (SUPERADMIN/ADMINISTRADOR siempre
  obligatorio) y `CONTEXTOS_SIN_MFA` (api/m2m/autocobro/kiosco). El FACTOR es del usuario; la POLÍTICA
  es de la empresa. Permisos RBAC `mfa.*` en `seguridad/catalogo.py`.
- **Decisión adaptativa (`mfa_decision.evaluar`)**: punto único que combina política + factor activo +
  dispositivo de confianza → `{reto_requerido, obligatorio, debe_enrolar}`. Lo usan el login de
  escritorio (`main.py`) y `/auth/login`.
- **Login humano API (`api/routers/auth.py`)**: `/auth/login` NO emite JWT completo si hay 2º factor
  activo → `mfa_required` + `mfa_token` (`type='mfa_pending'`, rechazado por el guard `access`); el JWT
  completo se emite en `/auth/mfa` (TOTP/recovery) con claims `amr:["pwd","otp"]`+`mfa`+**`auth_time`**.
  El login solo-contraseña lleva `amr:["pwd"]`+`auth_time` y, si la política obliga y el usuario no tiene
  factor, el claim `enrollment_required`. **`/auth/step-up`** refresca `auth_time` con un 2º factor.
  Rate-limit en `/auth/mfa` y `/auth/step-up`. **API keys / M2M NO pasan por MFA.**
- **Guard de step-up API (`api/security.requiere_step_up`)**: decorador para endpoints SENSIBLES; exige
  identidad humana con MFA reciente derivado del token real (`mfa`+`auth_time`, `tokens.mfa_reciente`);
  M2M (`auth='apikey'`) pasa. Equivalente conceptual a `pedir_step_up` en escritorio.
- **Enrolamiento obligatorio**: `mfa_decision.debe_enrolar` (política obliga + sin factor) fuerza el
  alta en el login de escritorio (`main.py._enrolar_mfa_obligatorio`) y marca `enrollment_required` en
  la API; los endpoints sensibles lo exigen. Un login con MFA correcto registra MFA reciente
  (`mfa_stepup.registrar`).
- **Enrolamiento UI (`gui/mfa_gui.py` → pestaña "SEGURIDAD (MFA)" en Configuración)**: activar/estado/
  desactivar (respeta política obligatoria + reauth) / recovery codes (una vez) / regenerar.
- **Reset admin (`mfa_admin.py`)**: permiso `mfa.admin.reset` + reauth + step-up + evento `MFA_RESET`.
- **Dispositivos de confianza (`mfa_dispositivos.py`, migr 0161)**: capa sobre `ioc_terminales`
  (usuario+empresa+`codigo_terminal`, caducable/revocable). En un terminal validado no se re-pide el 2º
  factor (TPV/PDA); PIN operativo/cambio de cajero intactos.
- **WebAuthn/Passkeys (`mfa_webauthn.py`, migr 0162, endpoints `/auth/webauthn/*`)**: relying party
  DEGRADABLE (librería `webauthn`), adicional a TOTP; guarda SOLO datos públicos (nunca claves
  privadas). La ceremonia es de navegador; el escritorio conserva TOTP como fallback.
- **Step-up (`mfa_stepup.py`)**: `pedir_step_up(usuario, accion)` (guard ÚNICO de escritorio) exige MFA
  reciente (ventana efímera en memoria, caduca, por usuario+empresa) para `ACCIONES_CRITICAS` (registro
  centralizado). Un recovery code NO vale como step-up de alto riesgo salvo que la política de la empresa
  lo permita (`metodos` incluye `recovery`). Eventos `STEP_UP_REQUIRED/SUCCESS/FAILURE`.
- **Auditoría (`mfa_eventos.py`)**: taxonomía canónica (`MFA_ENROLLED`/`CHALLENGE`/`SUCCESS`/`FAILURE`/
  `RESET`/`RECOVERY_USED`/`TRUSTED_DEVICE_*`/`MFA_POLICY_CHANGED`) sobre `log_auditoria`+`registrar_evento`,
  con saneado que **nunca** registra secretos.

- **Cableado de acciones críticas de negocio (fase final)**: las 12 `ACCIONES_CRITICAS` están conectadas
  al guard oficial. Escritorio usa **`gui/mfa_gui.step_up_sesion(accion)`** (atajo de `pedir_step_up` que
  toma el usuario de `sesion_global`) en el chokepoint de cada acción, **después** de RBAC: `roles.cambiar`
  (`seguridad_gui._nuevo_rol/_asignar/_desasignar`), `permisos.cambiar` (`seguridad_gui._conceder/_quitar`),
  `pagos.pasarela.configurar` (`tpv._PasarelaConfigDialog._guardar`), `canal_web.dominios`
  (`tpv._acc_*_dominio`), `saas.admin` (`saas_admin._cambiar_plan/_renovar`), `finanzas.critica`
  (`tesoreria_gui._generar_remesa`), `email.cambiar` (`gestion_usuarios._de_guardar_empresa`, solo si cambia
  el correo). `secretos.acceder` NO tiene superficie (secretos *write-only*; `obtener_secreto` es interno/M2M
  → gate reservado, no cablear). Ninguna de las 8 tiene endpoint REST humano hoy; `requiere_step_up` queda
  listo para cuando se expongan. NUNCA crear endpoints/tablas/motores nuevos para esto.

Reglas permanentes: un solo motor TOTP (`mfa.py`); jamás secretos en claro ni en logs; API keys sin MFA
humano; el dispositivo de confianza no es bypass universal ni elimina el step-up de acciones críticas.

### AI Forecasting

`src/gui/informe_reposicion.py` calls `predecir_ventas_semanales()` using Facebook Prophet. It also calls `verificar_ia_reposicion()` to raise smart stock alerts. Prophet is an optional dependency; the app degrades gracefully if unavailable.

**Honestidad IA/ML (Fase capacidades avanzadas)**: el motor predictivo por defecto (`services/prediccion/
heuristicas`) es HEURÍSTICO (media móvil + proyección lineal), con `Estimador` enchufable (`set_estimador`
→ Prophet/XGBoost/…). Usar `heuristicas.motor_activo() → {motor, tipo:'heuristica'|'ml', es_ml}` para
etiquetar el ORIGEN: la UI/SOMA/dashboards NUNCA deben presentar una heurística como "IA/ML". Estado real de
las 8 capacidades avanzadas (IA/tiempo real/multiplataforma/Canal Web/cloud/conectores/API pública) en
`CERTIFICACION_CAPACIDADES_AVANZADAS.md`: solo API pública es 🟢 operativa aquí; el resto tiene bloqueos
externos (hardware/hosting/infra cloud/credenciales) y se marca roadmap/preparado — NO falsear con mocks.

### Producción / MRP (OPERATIVO — cierre de brecha, iteración 1)

El motor MRP vive en `src/services/mrp/` (`bom, ordenes, costes, centros, mps, planificador, produccion_pro,
analitica`) — completo y con el ciclo de OF cableado al **motor oficial** de existencias (`db/kardex`
SALIDA_PRODUCCION/ENTRADA_PRODUCCION, `db/lotes` FEFO), auditado (`FAB_*`), idempotente. La GUI operativa está
en `gui/mrp_dashboard.py`: `ProduccionWindow` (ruta de menú **`produccion`**, tarjeta "Producción") con barra
de acciones sobre Órdenes de Fabricación (Nueva OF/Planificar/Liberar/Iniciar/Pausar/Consumir/Producir/
Finalizar/Cancelar) + alta de BOM. **Regla permanente**: la GUI SOLO orquesta; toda la lógica sigue en
`services/mrp`; el stock usa EXCLUSIVAMENTE `ordenes.consumir_materiales`/`registrar_produccion` (nunca un
motor de stock paralelo); RBAC único vía `services.autorizacion.puede` con permisos `mrp.ver/bom/planificar/
admin`.

**Calidad (OPERATIVO — iteración 2)**: motor en `src/services/calidad/` (`inspecciones, no_conformidades,
capa, auditorias, trazabilidad`); GUI operativa en `gui/calidad_dashboard.py` (`CalidadDashboardWindow`,
ruta de menú **`calidad`**, tarjeta "Calidad"): inspecciones (recepción/producción/final, **el rechazo
abre NC automáticamente** — integración Compras→Calidad ya en backend), ciclo NC (abierta→en_análisis→
accionada→cerrada/rechazada) y CAPA (abierta→en_curso→cerrada[eficacia]/cancelada). RBAC `inspecciones.crear`,
`nc.crear`, `calidad.admin`. Nota: `inspector`/`responsable` son columnas INT (id de usuario).

**GMAO (OPERATIVO — iteración 3)**: motor en `src/services/gmao/` (`activos, planes, ordenes, analitica`);
GUI operativa en `gui/gmao_dashboard.py` (`GMAODashboardWindow`, ruta de menú **`gmao`**, tarjeta
"Mantenimiento"): activos, mantenimiento preventivo (planes → generación de OT vencidas) y correctivo
(OT→técnico→**repuesto por kárdex oficial** `consumir_repuestos`→cierre con costes). RBAC `activos.gestionar`,
`ot.crear`, `gmao.admin`; `tecnico`/`responsable` son INT. **Lección PyQt (permanente)**: NO conectar como
slot directo (`clicked.connect`) un método cuyo nombre contenga caracteres no-ASCII (p. ej. `ñ`) — provoca
**segfault** en SIP; usar nombres ASCII o envolver en `lambda`.

**SAT/Helpdesk (OPERATIVO núcleo — iteración 4)**: motor en `src/services/sat/` (`tickets, intervenciones,
contratos_sla, sat_pro, kb`); GUI operativa en `gui/sat_dashboard.py` (`SATDashboardWindow`, ruta de menú
**`sat`**, tarjeta "Soporte (SAT)"): tickets (ciclo abierto→…→cerrado + asignar técnico + comentar +
intervención), SLA/contratos y **bolsa de horas** (`sat_pro.consumir_horas` = facturación por horas). RBAC
`tickets.crear/gestionar`, `sat.admin`; `tecnico`/`autor` INT. **Honestidad**: el backend SAT NO consume
stock por repuestos ni genera factura comercial desde el ticket (no se inventó); la facturación real es la
bolsa de horas.

**Fiscal/AEAT (motor REAL EXPUESTO — iteración 5)**: OJO — el motor fiscal NO es un mock: `services/fiscal/
emisores/verifactu_aeat.py` envía por SOAP a los **endpoints OFICIALES de la AEAT**, `emisores/tls.py` hace
**mTLS real**, `certificados.py` gestiona el PKCS#12 cifrado, `worker.procesar_cola` transmite con máquina de
estados (generado→firmado→enviado→rechazado/anulado); `simulado` es solo el fallback sin certificado. La GUI
`gui/fiscal_gui.py` (`FiscalWindow`, ruta de menú **`fiscal`**, tarjeta "Fiscal") expone: gestión de
certificados (importar/activar/revocar, **nunca muestra el material**) + registros Verifactu + "Procesar cola
de envío". RBAC `aeat.presentar`. **INVARIANTE**: sin certificado de producción + alta AEAT, la transmisión
NO se acepta — nunca se simula 'enviado/aceptado' (lo fija el worker con el acuse REAL). Programa de cierre
de brechas: **5/5 áreas** hechas. Ver `CERTIFICACION_CIERRE_FISCAL_PRODUCCION_GMAO_CALIDAD_SAT.md`.

### RFID Integration

`src/utils/rfid_gateway.py` communicates with Zebra RFID readers over HTTP. `src/utils/rfid_worker.py` wraps this in a QThread. A simulated mode is available when hardware is absent.

## Output Files

Generated PDFs, labels, tickets, and reports are written to subdirectories under `documentos/` (albaranes, etiquetas, facturación, informes de reposición, QR ubicaciones, stocks, tickets).
