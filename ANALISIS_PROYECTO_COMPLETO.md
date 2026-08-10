# 📊 ANÁLISIS EXHAUSTIVO: SMART MANAGER AI

**Documento de análisis técnico detallado del proyecto Smart Manager AI**  
**Fecha**: 24 de junio de 2026  
**Descripción**: Sistema ERP completo de escritorio/SaaS para gestión de almacenes y retail con IA integrada

---

## 📋 Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Stack Tecnológico](#stack-tecnológico)
4. [Estructura del Proyecto](#estructura-del-proyecto)
5. [Módulos y Componentes](#módulos-y-componentes)
6. [Funcionalidades Principales](#funcionalidades-principales)
7. [Base de Datos](#base-de-datos)
8. [Integraciones Externas](#integraciones-externas)
9. [Autenticación y Seguridad](#autenticación-y-seguridad)
10. [Patrones de Código](#patrones-de-código)
11. [Deployment](#deployment)
12. [Información Adicional](#información-adicional)

---

## 🎯 Descripción General

### ¿Qué es Smart Manager AI?

**Smart Manager AI** es una **aplicación empresarial multiplataforma (Windows/Linux/Mac)** construida con **PyQt6**, diseñada para la **gestión integral de almacenes y retail con inteligencia artificial integrada**.

Es un sistema ERP completo que combina:
- 🏪 **Gestión de almacenes y tiendas**
- 💳 **Terminal de punto de venta (TPV) completa**
- 📦 **Control de inventario con RFID**
- 👥 **Gestión laboral y RRHH**
- 🤖 **IA integrada** (predicción de demanda, traducción, asistente de voz)
- 🌍 **Soporte para 20 idiomas**
- 📊 **Business Intelligence y análisis**
- 🔒 **Seguridad empresarial** (Argon2id, AES-256, auditoría completa)
- ☁️ **Versión SaaS multi-tenant disponible**

### Casos de Uso Principales

1. **Gestión de almacenes**: Recepción de palés, mapeo de ubicaciones, control de stock con RFID
2. **Punto de venta**: TPV completo con múltiples formas de pago (efectivo, tarjeta, Redsys)
3. **Control de inventario**: Stock físico, movimientos, trazabilidad, lotes con FEFO
4. **Gestión laboral**: Fichajes, horarios, nóminas, contratos
5. **Previsión de demanda**: IA con Facebook Prophet para predicciones automáticas
6. **Fiscalidad**: Soporte Verifactu (España), facturación digital, encadenado de hash
7. **Gestión de costos**: Mermas, devoluciones, análisis de pérdidas
8. **Comunicaciones**: Correo corporativo (Gmail OAuth), envío de documentos

---

## 🏗️ Arquitectura del Sistema

### Patrón Arquitectónico: Layered (Capas)

```
┌─────────────────────────────────────────────────────────┐
│         CAPA DE PRESENTACIÓN (PyQt6 GUI)               │
│              40+ módulos de interfaz                   │
├─────────────────────────────────────────────────────────┤
│         CAPA DE SERVICIOS (Lógica Empresarial)          │
│    Workflows, integraciones, IA, auditoría, RBAC       │
├─────────────────────────────────────────────────────────┤
│      CAPA DE DATOS (DB Layer - 46 módulos)             │
│         Pool de conexiones + Consultas SQL             │
├─────────────────────────────────────────────────────────┤
│    BACKEND OPCIONAL (Flask REST + Gunicorn)            │
│       API JSON, webhooks, SaaS multi-tenant            │
└─────────────────────────────────────────────────────────┘
     ↕
┌─────────────────────────────────────────────────────────┐
│    INFRAESTRUCTURA (MariaDB 11+, RFID, hardware)       │
└─────────────────────────────────────────────────────────┘
```

### Componentes Principales

#### **SmartManagerApp (src/main.py)**
- Clase raíz que hereda de `QStackedWidget` (navegación entre pantallas)
- Gestiona:
  - Pool de conexiones a MariaDB
  - Inicialización automática de BD (bootstrap)
  - Sistema de roles y autenticación
  - Hilo RFID para lectura en tiempo real
  - Asistente de voz SOMA
  - Notificaciones flotantes

#### **LoginWindow (src/gui/login.py)**
- Autenticación multiusuario
- Selector de 20 idiomas con cambio en caliente
- Bloqueo progresivo tras N intentos fallidos
- Migración transparente de hashes SHA-256 → Argon2id

#### **MenuPrincipal (src/gui/menu_principal.py)**
- Tarjetas dinámicas basadas en roles del usuario
- Acceso a 40+ módulos según permisos RBAC
- Logo corporativo personalizable
- Indicador de estado SOMA (inactivo/escuchando/activado/procesando)

---

## 🛠️ Stack Tecnológico

### Dependencias Principales

| Categoría | Componente | Versión | Propósito |
|-----------|-----------|---------|----------|
| **GUI** | PyQt6 | 6.9.1 | Interfaz de escritorio |
| **Runtime** | Python | 3.11+ | Lenguaje base |
| **BD** | MariaDB/MySQL | 11+ | Base de datos relacional |
| **DB Driver** | PyMySQL | 1.1.2 | Conexión MySQL |
| **Pool** | DBUtils | 3.1.2 | Pool de conexiones |

### Datos y Documentos

| Librería | Versión | Propósito |
|----------|---------|----------|
| pandas | 2.3.3 | ETL y análisis de datos |
| openpyxl | 3.1.5 | Lectura/escritura Excel |
| reportlab | 4.4.10 | Generación PDF (tickets, nóminas) |
| Pillow | 11.3.0 | Manipulación de imágenes |
| PyMuPDF | 1.26.6 | Render PDF avanzado |
| python-barcode | 0.16.1 | Generación de códigos de barras |
| qrcode | 8.2 | Generación de códigos QR |

### IA y Predicción

| Librería | Versión | Propósito |
|----------|---------|----------|
| anthropic | 0.105.2 | Traducción IA (Claude Haiku 4.5) |
| prophet | 1.1.7 | Previsión de demanda (Facebook) |
| matplotlib | 3.10.7 | Gráficas y dashboards |

### Backend y API

| Librería | Versión | Propósito |
|----------|---------|----------|
| Flask | 3.1.3 | Servidor REST |
| gunicorn | 21+ | WSGI application server |
| requests | 2.33.1 | Cliente HTTP |

### Seguridad y Criptografía

| Librería | Versión | Propósito |
|----------|---------|----------|
| cryptography | 46.0.7 | Cifrado AES, 3DES (pagos) |
| pyOpenSSL | 24.2.1 | mTLS sin PEM en disco |
| argon2-cffi | 25.1.0 | Hash de contraseñas Argon2id |
| PyJWT | 2.13.0 | Tokens JWT/refresh |
| signxml | 4.5.1 | Firma XAdES (Facturae) |

### Asistente de Voz SOMA

| Librería | Versión | Propósito |
|----------|---------|----------|
| edge-tts | 7.2.8 | Síntesis neural multivoz |
| pyttsx3 | 2.99 | Síntesis offline (respaldo) |
| SpeechRecognition | 3.16.1 | Reconocimiento de voz |
| pygame | 2.6.1 | Reproducción de audio |
| Unidecode | 1.3.8 | Romanización universal |

### Integraciones de Correo

| Librería | Versión | Propósito |
|----------|---------|----------|
| google-auth-oauthlib | 1.2.2 | OAuth 2.0 Google |
| google-api-python-client | 2.185.0 | API Gmail |

### Hardware

| Librería | Versión | Propósito |
|----------|---------|----------|
| opencv-python | 4.12.0.88 | Cámara (escaneo de códigos) |
| pyzbar | 0.1.9 | Decodificación de códigos de barras |
| pyserial | 3.5 | Báscula, periféricos serie |
| pyusb | 1.3.1 | Impresora térmica USB |

### Utilidades Varias

| Librería | Versión | Propósito |
|----------|---------|----------|
| python-dotenv | 1.2.2 | Carga de variables de entorno |
| watchdog | 6.0.0 | Vigilancia de archivos |
| numpy | 2.2.6 | Cálculos numéricos |

---

## 📁 Estructura del Proyecto

```
Smart Manager AI/
│
├── src/                              # 🔴 Código principal
│   ├── main.py                       # Punto de entrada
│   ├── autocobro_app.py              # Sistema de cobros automáticos
│   ├── generar_codigos.py            # Generación de códigos/referencias
│   │
│   ├── gui/                          # 40+ módulos de interfaz gráfica
│   │   ├── login.py                  # Autenticación + selector idioma
│   │   ├── menu_principal.py         # Navegación principal
│   │   ├── tpv.py                    # Terminal punto de venta
│   │   ├── ventas.py                 # Búsqueda y análisis
│   │   ├── recepcion_pale.py         # Recepción de palés (RFID)
│   │   ├── ubicacion_tienda.py       # Mapeo de ubicaciones
│   │   ├── stock_almacen_gui.py      # Control de stock
│   │   ├── etiquetas_precios.py      # Generación de etiquetas
│   │   ├── gestion_mermas.py         # Registro de pérdidas
│   │   ├── informe_reposicion.py     # Predicción IA con Prophet
│   │   ├── kardex_visor.py           # Historial de movimientos
│   │   ├── catalogo_gestion.py       # Gestión de artículos (ABM)
│   │   ├── clientes_gui.py           # Gestión de clientes
│   │   ├── rrhh_gestion.py           # Fichajes, horarios, nóminas
│   │   ├── gestion_usuarios.py       # RBAC y permisos
│   │   ├── bi_dashboard.py           # BI: ventas, margen, KPIs
│   │   ├── finanzas_dashboard.py     # Tesorería, flujo de caja
│   │   ├── crm_dashboard.py          # CRM: clientes, oportunidades
│   │   ├── gmao_dashboard.py         # Mantenimiento preventivo
│   │   ├── correo_corporativo.py     # Gmail OAuth
│   │   ├── notificaciones_gui.py     # Centro de notificaciones
│   │   └── [30+ módulos más]
│   │
│   ├── db/                           # 46 módulos de capa de datos
│   │   ├── conexion.py               # Pool de conexiones + bootstrap
│   │   ├── usuario.py                # Autenticación + sesión
│   │   ├── rbac.py                   # Roles y permisos
│   │   ├── articulos.py              # ABM artículos + precios
│   │   ├── stock.py                  # Stock por tienda
│   │   ├── stock_almacen.py          # Stock de almacén
│   │   ├── logistica.py              # Recepción, traspasos, palés
│   │   ├── mermas.py                 # Pérdidas documentadas
│   │   ├── ventas.py                 # Transacciones de venta
│   │   ├── compras.py                # Pedidos a proveedor
│   │   ├── pagos.py                  # Cobros y pagos
│   │   ├── facturas_cliente.py       # Facturación
│   │   ├── fiscal.py                 # Config fiscal + encadenado hash
│   │   ├── prevision.py              # Prophet + predicción
│   │   ├── clientes.py               # Gestión de clientes
│   │   ├── proveedores.py            # Gestión de proveedores
│   │   ├── rrhh.py                   # Nóminas, contratos
│   │   ├── caja.py                   # Caja + arqueos
│   │   ├── tesoreria.py              # Tesorería
│   │   ├── lotes.py                  # Lotes con FEFO
│   │   ├── kardex.py                 # Historial de movimientos
│   │   ├── operaciones.py            # Movimientos varios
│   │   ├── empresa.py                # Multitenancy
│   │   ├── tiendas.py                # Gestión de tiendas
│   │   └── [25+ módulos más]
│   │
│   ├── utils/                        # 31 módulos de utilidades
│   │   ├── i18n.py                   # Sistema de 20 idiomas
│   │   ├── ai_translator.py          # Traducción IA
│   │   ├── config.py                 # Configuración global
│   │   ├── logger.py                 # Logging centralizado
│   │   ├── rfid_gateway.py           # Comunicación Zebra RFID
│   │   ├── rfid_worker.py            # Hilo de lectura RFID
│   │   ├── soma_engine.py            # Parsing de comandos voz
│   │   ├── soma_tts.py               # Síntesis de voz
│   │   ├── soma_worker.py            # Hilo SOMA
│   │   ├── impresion.py              # Generación PDF
│   │   ├── perifericos.py            # Escpos, báscula, scanner
│   │   ├── cripto.py                 # Cifrado AES/3DES
│   │   ├── divisas.py                # Conversión de monedas
│   │   ├── iban.py                   # Validación IBAN
│   │   ├── fiscalidad.py             # IVA, retenciones
│   │   └── [16+ módulos más]
│   │
│   ├── services/                     # Servicios empresariales
│   │   ├── autorizacion.py           # Motor RBAC
│   │   ├── scheduler.py              # Tareas programadas (APScheduler)
│   │   ├── correo/                   # Gmail OAuth + SMTP
│   │   ├── fiscal/                   # Verifactu, Facturae
│   │   ├── bi/                       # Business Intelligence
│   │   ├── crm/                      # CRM avanzado
│   │   ├── gmao/                     # Mantenimiento preventivo
│   │   ├── mrp/                      # Planificación de producción
│   │   ├── sat/                      # Sistema antirrobo (RFID)
│   │   ├── dr/                       # Disaster Recovery
│   │   ├── saas/                     # Multi-tenant
│   │   ├── workflow/                 # Procesos customizables
│   │   └── [más subdirectorios]
│   │
│   ├── backend/                      # Backend Flask REST
│   │   ├── api.py                    # Endpoints REST
│   │   ├── app.py                    # Factory Flask
│   │   └── storefront.py             # Frontend API
│   │
│   ├── database/                     # SQL bootstrap
│   │   └── bootstrap_mariadb.sql     # Inicialización de tablas
│   │
│   ├── rrhh/                         # Datos de RRHH
│   ├── seguridad/                    # Autenticación, auditoría
│   └── models/                       # (Preparado para futuro)
│
├── assets/                           # Recursos globales
│   ├── estilo_global.py              # Tema oscuro + cyan (#00FFC6)
│   ├── lang/                         # 20 archivos JSON de idiomas
│   │   ├── es.json, en.json, fr.json, de.json, it.json, pt.json
│   │   ├── zh.json, ja.json, ko.json, hi.json, ar.json
│   │   ├── ru.json, tr.json, nl.json, pl.json, id.json
│   │   ├── vi.json, th.json, uk.json, sv.json, ca.json
│   │
│   ├── currencies/                   # Datos de 20 monedas
│   │   ├── registry.json
│   │   ├── USD/, EUR/, GBP/, JPY/, ...
│   │
│   ├── flags/                        # Banderas PNG por idioma
│   ├── logos_institucionales/        # Logos corporativos
│   └── rrhh/                         # Datos de cotización social
│
├── documentos/                       # Salida de documentos generados
│   ├── Tickets/                      # PDFs de venta
│   ├── albaranes/                    # Remisiones
│   ├── facturacion/                  # Facturas
│   ├── informes_reposicion/          # Reportes IA
│   ├── mermas/                       # Reportes de pérdidas
│   ├── stocks/                       # Reportes de inventario
│   ├── backups/                      # Snapshots de BD
│   └── [20+ directorios más]
│
├── deploy/                           # Configuración de despliegue
│   └── k8s/                          # Manifiestos Kubernetes
│
├── docs/                             # Documentación técnica
│   ├── api.md                        # Endpoints REST
│   ├── conexiones.md                 # Config BD
│   ├── fiscal.md                     # Verifactu/Facturae
│   ├── migraciones.md                # Migraciones schema
│   ├── seguridad.md                  # Arquitectura seguridad
│   ├── tenancy.md                    # Multitenancy
│   ├── testing.md                    # Estrategia testing
│   └── RUNBOOK_BACKUP.md             # Procedimientos backup
│
├── tests/                            # Suite de pruebas
│   ├── conftest.py                   # Fixtures pytest
│   ├── factories.py                  # Factories de datos
│   ├── smoke_test.py                 # Tests sin BD
│   ├── unit/                         # Pruebas unitarias
│   └── integration/                  # Pruebas integración
│
├── pyproject.toml                    # Config herramientas (ruff, pytest)
├── requirements.txt                  # Dependencias Python (60+)
├── requirements-dev.txt              # Dependencias desarrollo
├── docker-compose.yml                # Orquestación (SaaS)
├── docker-compose.prod.yml           # Composición producción
├── Dockerfile                        # Imagen Docker backend
├── wsgi.py                           # Entry point Gunicorn
├── SmartManagerAI.spec               # Spec para PyInstaller
├── build.bat                         # Script de compilación
├── Dockerfile                        # Containerización
├── CLAUDE.md                         # Guía para Claude AI
├── README.md                         # Documentación general
└── .env.example                      # Plantilla de variables

```

---

## 🔌 Módulos y Componentes Detallados

### 6.1 CAPA DE PRESENTACIÓN (src/gui/ — 40+ módulos)

#### Módulos de Negocio Principal

| Módulo | Propósito | Funcionalidades |
|--------|----------|-----------------|
| **tpv.py** | Terminal punto de venta | Búsqueda rápida, carrito, 5+ formas pago, devoluciones, ticket PDF |
| **recepcion_pale.py** | Recepción de palés | Lectura RFID/QR, mapeo automático, recuentos |
| **ubicacion_tienda.py** | Mapa de ubicaciones | Visualización QR, RFID, gestión de zonas |
| **stock_almacen_gui.py** | Stock por almacén | Consulta, visualización, alertas |
| **importar_stock.py** | Importación en lote | Excel → BD, validación, logging |
| **etiquetas_precios.py** | Etiquetas de precio | Generación PDF, impresión térmica |
| **gestion_mermas.py** | Registro de pérdidas | Documentación, causas, análisis |
| **informe_reposicion.py** | Predicción IA | Prophet, alertas inteligentes, weekly forecast |
| **kardex_visor.py** | Historial | Movimientos INV, trazabilidad |
| **lotes_caducidades.py** | Gestión FEFO | Lotes, vencimientos, alertas |
| **catalogo_gestion.py** | ABM artículos | Crear, editar, eliminar, precios |
| **clientes_gui.py** | Gestión clientes | CRM básico, contactos, histórico |
| **compras_gestion.py** | Pedidos proveedor | OC, recepción, facturación |
| **rrhh_gestion.py** | Laboral | Fichajes, horarios, nóminas, contratos |
| **gestion_usuarios.py** | RBAC | Usuarios, roles, permisos |
| **bi_dashboard.py** | BI ventas | KPIs, margen, top productos |
| **finanzas_dashboard.py** | Tesorería | Flujo de caja, análisis |
| **crm_dashboard.py** | CRM | Clientes, oportunidades |
| **correo_corporativo.py** | Correo | Gmail OAuth, envío documentos |

### 6.2 CAPA DE DATOS (src/db/ — 46 módulos)

#### Módulos de Dominio

| Módulo | Responsabilidad | Tablas |
|--------|-----------------|--------|
| **conexion.py** | Pool de conexiones, bootstrap | Gestión de conexiones |
| **usuario.py** | Autenticación, sesión | usuarios, sesiones |
| **rbac.py** | Roles y permisos | roles, permisos, usuarios_roles |
| **articulos.py** | ABM productos | articulos, articulos_tienda, precios |
| **stock.py** | Stock por tienda | stock_tienda |
| **logistica.py** | Recepción, traspasos | recepciones, traspasos |
| **mermas.py** | Pérdidas | mermas, mermas_detalles |
| **ventas.py** | Transacciones venta | ventas, venta_items |
| **compras.py** | Pedidos proveedor | compras, compras_items |
| **pagos.py** | Cobros y pagos | pagos, pagos_detalles |
| **facturas_cliente.py** | Facturación | facturas, facturas_items |
| **fiscal.py** | Config fiscal | fiscal_config, fiscal_registros |
| **prevision.py** | Predicción demand | predictiones |
| **clientes.py** | Gestión clientes | clientes, contactos |
| **proveedores.py** | Gestión proveedores | proveedores, contactos_prov |
| **caja.py** | Caja y arqueos | caja, arqueos |
| **tesoreria.py** | Tesorería | tesoreria, conciliacion |
| **lotes.py** | Lotes, FEFO | lotes, lotes_articulos |
| **kardex.py** | Historial movimientos | kardex |
| **empresa.py** | Multitenancy | empresas |

### 6.3 CAPA DE UTILIDADES (src/utils/ — 31 módulos)

| Módulo | Propósito |
|--------|----------|
| **i18n.py** | Sistema de 20 idiomas, cambio en caliente |
| **ai_translator.py** | Traducción IA (Claude Haiku) |
| **rfid_gateway.py** | Comunicación Zebra FX/RFD |
| **rfid_worker.py** | Hilo de lectura RFID (signals/slots) |
| **soma_engine.py** | Parsing de comandos voz con IA |
| **soma_tts.py** | Síntesis neural (edge-tts) |
| **soma_worker.py** | Hilo SOMA (escucha + síntesis) |
| **impresion.py** | Generación PDF multiidioma |
| **perifericos.py** | Escpos, báscula, scanner |
| **cripto.py** | Cifrado AES, 3DES |
| **divisas.py** | Conversión de monedas |
| **fiscalidad.py** | IVA, retenciones por país |

---

## ⚡ Funcionalidades Principales

### 1️⃣ Gestión de Inventario
- ✅ Stock por tienda (persistencia isolada)
- ✅ Recepción de palés con QR/RFID
- ✅ Traspasos entre almacenes
- ✅ Recuento físico asistido
- ✅ Kardex (historial de movimientos)
- ✅ Lotes con FEFO (First Expire First Out)
- ✅ Alertas de caducidad automáticas
- ✅ Mermas (documentadas y trazables)
- ✅ Predicción IA de reabastecimiento

### 2️⃣ Punto de Venta (TPV)
- ✅ Búsqueda rápida (RFID/barras/manual)
- ✅ Carrito de compra dinámico
- ✅ 5+ formas de pago: efectivo, tarjeta, Redsys, mixto, vales
- ✅ Descuentos por cliente/artículo/grupo
- ✅ Devoluciones integradas
- ✅ Generación de ticket PDF multiidioma
- ✅ Display cliente (periférico)
- ✅ Impresora térmica ESC/POS
- ✅ Cierre de caja con arqueo

### 3️⃣ Gestión Fiscal & Facturación
- ✅ Facturación digital (Facturae XAdES)
- ✅ Soporte Verifactu (España)
- ✅ Encadenado de hash (cadena inalterable)
- ✅ Retenciones por país (IRPF, IGIC, etc.)
- ✅ IVA multijurisdiccional
- ✅ SEPA (transferencias)
- ✅ Integración AEAT (validación CIF)

### 4️⃣ Laboral & RRHH
- ✅ ABM empleados completo
- ✅ Fichajes (entrada/salida automática)
- ✅ Gestión de horarios y turnos
- ✅ Nóminas generadas PDF
- ✅ Contratos laborales (templates)
- ✅ Cálculo de cotización social
- ✅ Portal de autoservicio empleado

### 5️⃣ IA & Predicción
- ✅ Prophet: Previsión semanal de ventas
- ✅ Alertas inteligentes de reabastecimiento
- ✅ Traducción dinámica (IA Level 2)
- ✅ Asistente de voz SOMA (IA Level 3)

### 6️⃣ Hardware Integration
- ✅ RFID Zebra FX/RFD (lectura/escritura EPC)
- ✅ Cámara USB (escaneo visual)
- ✅ Impresora térmica (ESC/POS)
- ✅ Báscula digital (serie)
- ✅ Display cliente TCP/USB
- ✅ Modo simulado sin hardware

### 7️⃣ Comunicaciones
- ✅ Correo corporativo (Gmail OAuth 2.0)
- ✅ Envío de albaranes/informes
- ✅ SMTP con autenticación
- ✅ Webhooks de pago (Redsys)
- ✅ Notificaciones integradas

### 8️⃣ Seguridad & Auditoría
- ✅ Autenticación multiusuario (Argon2id)
- ✅ RBAC (roles: ADMINISTRADOR, GERENTE, OPERARIO)
- ✅ Bloqueo progresivo tras fallos
- ✅ Log completo de operaciones
- ✅ Cifrado en reposo (AES-256)
- ✅ mTLS sin PEM en disco
- ✅ Firma XAdES (documentos)

### 9️⃣ Análisis & BI
- ✅ Dashboard de ventas (KPIs)
- ✅ Análisis de margen
- ✅ Reportes de inventario
- ✅ Histórico de compras
- ✅ Análisis por vendedor
- ✅ Gráficas con matplotlib

### 🔟 Configuración & Admin
- ✅ Multiidioma 20 idiomas (cambio en caliente)
- ✅ Multiempresa (EMPRESA_DEFAULT_ID)
- ✅ Multisltienda (tienda activa por sesión)
- ✅ Logo corporativo (upload)
- ✅ Configuración fiscal por territorio
- ✅ Estilo global personalizable
- ✅ Backups automáticos

---

## 🗄️ Base de Datos

### Estructura MariaDB

#### Tablas Principales

| Tabla | Propósito | Escala |
|-------|----------|--------|
| **usuarios** | Autenticación + sesión | 50-500 registros |
| **articulos** | Catálogo de productos | 1K-100K |
| **stock_tienda** | Stock por tienda (desnormalizado) | 1K-100K |
| **ventas** | Transacciones de venta | 10K-1M |
| **venta_items** | Líneas de venta | 50K-5M |
| **compras** | Pedidos a proveedor | 1K-10K |
| **mermas** | Pérdidas documentadas | 1K-10K |
| **kardex** | Historial de movimientos | 100K-1M |
| **clientes** | Base de clientes | 1K-100K |
| **proveedores** | Base de proveedores | 100-1K |
| **empresas** | Multitenancy (tenant root) | 1-100 |
| **fiscal_config** | Configuración fiscal | 1-100 |
| **fiscal_registros** | Encadenado hash | 1K-100K |

### Inicialización Automática

```bash
1. ¿Existe DB "smart_manager_db"? NO
2. Ejecutar bootstrap_mariadb.sql
3. Crear todas las tablas + índices
4. Insertar datos de prueba (seed)
5. Crear empresa por defecto
6. Crear tienda por defecto
```

### Multitenancy

Cada registro está marcado por `id_empresa` e `id_tienda`:

```sql
INSERT INTO articulos 
  (id_empresa, id_tienda, codigo, nombre, stock)
VALUES 
  ('00000000-0000-0000-0000-000000000001', 1, 'ART001', 'Zapatos', 100)
```

---

## 🔗 Integraciones Externas

### Hardware

#### Zebra RFID Gateway
- **Protocolo**: HTTP REST
- **Operaciones**: 
  - `escribir_tag(epc)` → Grabar EPC
  - `leer_tag()` → Leer EPC cercano
  - `generar_epc_manual(nombre_ref)` → ID automático
- **Modo**: Simulado o hardware real
- **Clase**: `LectorZebraGateway` (src/utils/rfid_gateway.py)

#### Periféricos
- **Impresora térmica** (ESC/POS): USB directo
- **Escáner QR/códigos**: OpenCV + pyzbar
- **Báscula digital**: Serie (pyserial)
- **Display cliente**: TCP o USB
- **Cámara**: OpenCV

### Servicios Cloud

#### Gmail (OAuth 2.0)
- Autenticación delegada
- Lectura IMAP + sincronización
- API Gmail para envío
- Tokens encriptados en BD

#### Anthropic (IA)
- **Modelo**: Claude Haiku 4.5
- **Usos**: Traducción dinámica, respuestas SOMA

#### Redsys (Pagos)
- **Protocolo**: HTTP POST
- **Autenticación**: Firma 3DES + MAC
- **Webhooks**: Confirmación de pago
- **Cifrado**: AES-256

### API Interna (Backend Flask)

```
GET    /api/articulos          → Lista artículos
POST   /api/login              → Autenticación
GET    /api/stock/<codigo>     → Stock
POST   /api/ventas             → Registrar venta
GET    /api/facturas/<id>      → Factura PDF
```

---

## 🔐 Autenticación y Seguridad

### Sistema de Autenticación

#### Flujo Login
```
1. Usuario + Password
2. Validar en BD (usuarios.password, usuarios.bloqueado_hasta)
3. Comparar con Argon2id (o rehashear si SHA-256 legacy)
4. ¿Bloqueado por intentos? → Mostrar timer
5. ✓ Exito → SesionUsuario.instancia() + último_login
```

#### Bloqueo Progresivo

| Intentos | Bloqueo |
|----------|---------|
| 0-4 | Sin bloqueo |
| 5 | 1 minuto |
| 6 | 5 minutos |
| 7+ | 15 minutos |

#### Migración Transparente de Hashes
- Login con SHA-256 legacy
- Validar contraseña
- Si válida → rehashear a Argon2id
- Guardar en BD
- Próximo login usa Argon2id

### Roles y Permisos (RBAC)

| Rol | Permisos | Módulos |
|-----|----------|---------|
| **ADMINISTRADOR** | Todos | Todos (40+) |
| **GERENTE** | Lectura/escritura operaciones | Ventas, stock, reportes |
| **OPERARIO** | Lectura limitada | TPV, stock básico |

### Almacenamiento Seguro

- **Contraseñas**: Argon2id (salt incluido)
- **Datos sensibles**: AES-256 en reposo
- **Comunicación**: mTLS (certificados en memoria)
- **Tokens**: JWT con expiry
- **Auditoría**: Log completo en `seguridad/`

---

## 💡 Patrones de Código

### Singleton (Sesión Global)
```python
class SesionUsuario:
    _instancia = None
    
    @classmethod
    def instancia(cls):
        if not cls._instancia:
            cls._instancia = cls()
        return cls._instancia

sesion_global = SesionUsuario.instancia()
```

### Context Manager (Transacciones)
```python
@contextmanager
def transaccion():
    conn = obtener_conexion()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

### Signal/Slot (PyQt6 Threading)
```python
# Worker
tag_leido = pyqtSignal(str)
self.tag_leido.emit("3G0E0000ABCD1234")

# UI
worker.tag_leido.connect(self.on_tag_leido)
```

### Degradación Elegante
```python
try:
    from prophet import Prophet
except ImportError:
    Prophet = None

if Prophet and len(serie) >= 30:
    # Usar Prophet
else:
    # Media móvil simple
    return media * dias
```

### Multitenancy
```python
def obtener_articulos():
    emp, tnd = empresa_actual_id(), tienda_actual_id()
    cursor.execute(
        "SELECT * FROM articulos WHERE id_empresa=%s AND id_tienda=%s",
        (emp, tnd))
```

---

## 🚀 Deployment

### Desarrollo (Escritorio)

```bash
# Requiere:
# - Python 3.11+
# - MariaDB 11+ (mariadb-server)
# - .env en raíz

python src/main.py
```

### Compilación a Ejecutable

```bash
pyinstaller SmartManagerAI.spec
→ dist/SmartManagerAI.exe
```

Incluye:
- PyQt6 runtime completo
- Bootstrap de BD
- Activos (logos, idiomas, fuentes)
- Backend Flask (opcional)

### Docker (SaaS)

```bash
# Build
docker build -t smart-manager:latest .

# Compose
docker-compose up -d
# Servicios: Backend (Flask), BD (MariaDB), Backup

# Producción
docker-compose -f docker-compose.prod.yml up -d
```

### Kubernetes (Enterprise)

```bash
kubectl apply -f deploy/k8s/
# Manifiestos para:
# - Deployment Backend
# - StatefulSet MariaDB
# - ConfigMaps (config)
# - Secrets (credenciales)
# - PVC (persistencia)
```

---

## 📊 Sistema de Voz SOMA

**SOMA** = "Smart Operations Management Assistant"

### Componentes
- **Edge-TTS**: Síntesis neural multivoz (español, inglés, chino, etc.)
- **SpeechRecognition**: Reconocimiento (Google Speech-to-Text)
- **soma_engine.py**: Parsing de comandos (accent-insensitive)
- **soma_worker.py**: Hilo de escucha + respuesta

### Comandos Ejemplo
```
"Abre TPV"                    → Navega a TPV
"¿Cuántas unidades ART001?"   → Consulta stock
"Cierra stock"                → Cierra módulo
"Ayuda en TPV"                → Muestra comandos
```

### Estados
- 🔘 Inactivo (gris)
- 🔵 Escuchando (cyan pulsante)
- 🟢 Activado (cyan brillante)
- 🟠 Procesando (naranja)
- 🔴 Error (rojo)

---

## 🌍 Soporte Multiidioma (20 Idiomas)

```
🇪🇸 Español         🇬🇧 English        🇨🇳 中文
🇮🇳 हिन्दी           🇸🇦 العربية       🇵🇹 Português
🇫🇷 Français        🇷🇺 Русский       🇯🇵 日本語
🇩🇪 Deutsch         🇮🇹 Italiano      🇰🇷 한국어
🇹🇷 Türkçe          🇳🇱 Nederlands    🇵🇱 Polski
🇺🇦 Українська      🇮🇩 Indonesia     🇻🇳 Tiếng Việt
🇹🇭 ไทย             🇸🇪 Svenska       🇪🇸 Català
```

**Características**:
- Cambio en caliente (sin reiniciar)
- Fuentes Unicode automáticas para CJK/árabe/cirílico
- RTL (right-to-left) para árabe, hebreo
- Traducción IA Level 2 con Claude

---

## ✅ Testing

### Estructura

```
tests/
├── conftest.py              # Fixtures pytest
├── factories.py             # Factories de datos
├── smoke_test.py            # Tests sin BD
├── unit/                    # Pruebas unitarias
└── integration/             # Pruebas integración
```

### Cobertura

```bash
pytest --cov=src --cov-report=html
```

Excluidos:
- `src/gui/*` (UI Qt)
- `src/main.py` (bootstrapping)

---

## 📈 Escalabilidad

- **Pool de conexiones**: DBUtils (evita conexiones redundantes)
- **Caché i18n**: Catálogos en memoria
- **Señales Qt**: Threading sin deadlocks
- **Predicción Prophet**: Modelos cacheados
- **Lazy loading**: SOMA, IA, hardware (solo si se usan)

---

## 📚 Documentación

```
docs/
├── api.md                   # Endpoints REST
├── conexiones.md            # Config BD
├── fiscal.md                # Verifactu/Facturae
├── migraciones.md           # Migraciones schema
├── seguridad.md             # Arquitectura seguridad
├── tenancy.md               # Multitenancy
├── testing.md               # Estrategia testing
└── RUNBOOK_BACKUP.md        # Procedimientos backup
```

---

## 🎯 Resumen Ejecutivo

### ✅ Fortalezas Arquitectónicas

- **Modular**: 46 módulos BD + 40 GUI completamente aislados
- **Seguro**: Argon2id, AES-256, mTLS, auditoría completa
- **Multitenancy**: Aislamiento total empresa/tienda
- **IA integrada**: Prophet + Claude (traducción, comandos voz)
- **i18n**: 20 idiomas con cambio en caliente
- **Hardware**: RFID, impresoras, scanners, periféricos
- **Resiliente**: Degradación elegante de dependencias opcionales
- **Cloud-ready**: Backend Flask + Docker + Kubernetes

### 📈 Números Clave

- **40+ módulos GUI** (PyQt6)
- **46 módulos BD** (dominio-driven)
- **31 utilidades** (reutilizables)
- **14+ servicios empresariales**
- **20 idiomas soportados**
- **60+ dependencias Python**
- **100%+ funcionalidades retail/almacén**

### 🔮 Áreas de Mejora Futura

- OpenTelemetry (observabilidad completa)
- Type hints exhaustivos
- API GraphQL (además de REST)
- Offline-first con sincronización
- Aplicación mobile companion

---

## 🏁 Conclusión

**Smart Manager AI** es un **sistema ERP completo de escritorio/SaaS** para retail y almacenes con:
- ✅ Arquitectura modular y escalable
- ✅ Inteligencia artificial integrada (Prophet, Claude)
- ✅ Seguridad empresarial de clase mundial
- ✅ Soporte multiidioma y multitenant
- ✅ Integraciones hardware profesionales
- ✅ Código bien organizado y documentado
- ✅ **Listo para producción**

El proyecto demuestra **excelentes prácticas de ingeniería**, con separación de responsabilidades clara, patrones de diseño establecidos y degradación elegante de dependencias opcionales.

---

**Documento generado**: 24 de junio de 2026  
**Versión del análisis**: 1.0  
**Para consultas**: Consultar archivos de documentación en `docs/` o `CLAUDE.md`
