# Memoria Descriptiva y Justificativa del Software

**Documento preparado para su presentación ante el Registro de la Propiedad Intelectual
(Derechos de Autor sobre obra de software), conforme al Real Decreto Legislativo 1/1996, de 12 de
abril, por el que se aprueba el Texto Refundido de la Ley de Propiedad Intelectual (LPI), Título
VII (Programas de Ordenador).**

---

## 1. Título del programa

**Smart Manager**

## 2. Autor(es)

Mohamed Assbai Ahammar

---

## 3. Descripción general

Smart Manager es un sistema de planificación de recursos empresariales (ERP) integral, concebido
originalmente para la gestión de almacén y retail (recepción de mercancía, ubicación física,
control de stock y punto de venta) y ampliado hasta cubrir la práctica totalidad de los procesos
operativos, comerciales, financieros, fiscales y de recursos humanos de una pyme o empresa mediana
con varias tiendas o almacenes. Se distribuye como aplicación de escritorio para Windows, con una
capa de API REST propia, un cliente móvil nativo y una infraestructura cloud para los componentes
que operan en modo SaaS multiempresa.

El objetivo principal del programa es sustituir la combinación fragmentada de hojas de cálculo,
terminales de punto de venta aislados, gestorías externas para la contabilidad y software de
terceros no integrado entre sí, por un **modelo de datos único y compartido** entre todos los
módulos: el mismo artículo, cliente, proveedor, empleado y asiento contable se referencian de forma
consistente desde cualquier pantalla de la aplicación. Sobre ese modelo de datos común se apoyan
motores de negocio de desarrollo propio para las funciones más críticas: reglas de autorización
granular, generación y transmisión fiscal real ante la Agencia Tributaria (AEAT), planificación de
producción, mantenimiento de activos, calidad, soporte postventa, previsión de demanda y un
asistente conversacional propio que orquesta y explica el resto del sistema en lenguaje natural.

Smart Manager va dirigido a pequeñas y medianas empresas de distribución, retail y fabricación
ligera que necesitan gestionar de forma unificada su cadena de suministro, sus ventas, su
contabilidad y su cumplimiento fiscal digital, así como a los equipos internos (operarios de
almacén, personal de tienda, administración y dirección) que hoy dependen de herramientas
desconectadas entre sí para realizar ese mismo trabajo.

---

## 4. Funcionalidades principales

| Área | Funciones principales |
|---|---|
| **Operaciones de almacén/tienda** | Recepción de palés (con lectura RFID), mapeo de ubicaciones físicas (incluido posicionamiento GPS interno), kárdex de stock por lotes/caducidad (FEFO), inventario físico, traspasos entre almacenes, control de mermas |
| **Punto de venta (TPV)** | Venta con báscula/impresora térmica/escáner de código de barras, cobro (efectivo, tarjeta, pasarelas), devoluciones, modo autocobro |
| **Comercial / CRM** | Gestión de leads, oportunidades, pipeline y campañas; presupuestos y pedidos de cliente con conversión a venta; facturación, incluida factura electrónica (Facturae) y Verifactu |
| **Compras y proveedores** | Gestión de proveedores, pedidos de compra, portal extranet B2B propio para proveedores |
| **Contabilidad y finanzas** | Plan de cuentas, diario, mayor, balances, libros de IVA, cierres de ejercicio formales (con reapertura auditable), presupuestos para clientes, tesorería (cuentas, remesas SEPA, conciliación bancaria, previsión de caja) |
| **Fiscalidad** | Presentación de modelos AEAT (303, 390, 111, 190, 347, 349), emisión Verifactu con transmisión real ante los servidores oficiales de la AEAT, gestión de certificados digitales |
| **Recursos humanos** | Empleados, contratos, nóminas, altas y bajas, finiquitos, certificados, control horario |
| **Producción (MRP)** | Lista de materiales (BOM), órdenes de fabricación, planificación de la producción, centros de trabajo, cálculo de costes |
| **Mantenimiento (GMAO)** | Inventario de activos, planes de mantenimiento preventivo, órdenes de trabajo correctivas con consumo de repuestos |
| **Calidad** | Inspecciones de recepción, producción y final; gestión de no conformidades; ciclo de acciones correctivas y preventivas (CAPA); trazabilidad |
| **Soporte postventa (SAT)** | Tickets de incidencia, contratos de nivel de servicio (SLA), bolsa de horas facturables |
| **Inteligencia de negocio** | Panel ejecutivo, centro de actividad, previsión de demanda, simulador de escenarios |
| **Comercio digital** | Catálogo de producto centralizado, generación y publicación de canal web propio, conexión con plataformas externas y marketplaces |
| **Seguridad y control de acceso** | Roles de sistema con permisos granulares, concesiones individuales por usuario, listas de control de acceso por módulo y por sección interna, autenticación multifactor (TOTP y llaves de acceso/Passkeys), auditoría de eventos |
| **Asistente conversacional** | Asistente propio por voz y texto que interpreta preguntas en lenguaje natural sobre los datos del propio sistema y ejecuta acciones o navegación dentro de la aplicación |
| **Plataforma multiempresa** | Gestión de varias empresas/tiendas desde una misma instalación, licenciamiento y facturación por suscripción |
| **Cliente móvil** | Aplicación para picking, escaneo remoto, consulta de stock y pedidos, y gestión de incidencias y tareas de campo |

---

## 5. Lenguajes y tecnologías

| Categoría | Tecnología |
|---|---|
| Lenguaje principal (aplicación de escritorio) | Python 3.11 o superior |
| Interfaz gráfica de escritorio | PyQt6 |
| Backend HTTP / API REST | Flask, organizado en más de 40 módulos especializados por dominio funcional |
| Base de datos | MariaDB / MySQL, con acceso directo mediante consultas parametrizadas (sin capa ORM) y un gestor de conexiones propio |
| Cliente móvil | React Native con TypeScript |
| Generación de documentos | Generación de PDF propia para facturas, tickets, contratos, nóminas e informes |
| Empaquetado de la aplicación de escritorio | Compilación a ejecutable independiente para Windows |
| Infraestructura en la nube (modo multiempresa) | Servicios cloud gestionados mediante infraestructura como código, con base de datos gestionada y almacenamiento de objetos |
| Contenerización | Docker, para el despliegue de los componentes de servidor |

El sistema no emplea ningún framework de terceros para su lógica de negocio central: la
autorización de usuarios, la generación de la previsión de demanda, la comunicación fiscal con la
Agencia Tributaria y el asistente conversacional son motores de desarrollo propio, descritos con
más detalle en el apartado 7.

---

## 6. Requisitos del sistema

**Para el uso de la aplicación de escritorio (cliente principal):**

- Sistema operativo Windows.
- Intérprete de Python 3.11 o superior (o, alternativamente, el ejecutable ya compilado, que no
  requiere Python instalado en el equipo del usuario final).
- Servidor de base de datos MariaDB (o MySQL compatible) accesible en red, con un fichero de
  configuración de entorno que especifica host, usuario, contraseña, nombre de la base de datos y
  puerto de conexión.
- Conexión a Internet para las funciones que dependen de servicios externos (transmisión fiscal a
  la AEAT, sincronización de comercio digital, correo corporativo, asistente de voz, actualización
  de precios de mercado, etc.); la aplicación funciona en modo local para el resto de operaciones.
- Dependencias de software instalables mediante el gestor de paquetes de Python, entre las que
  destacan: interfaz gráfica (PyQt6), acceso a base de datos (PyMySQL), tratamiento de datos
  (pandas), generación de documentos (reportlab), tratamiento de imágenes (Pillow), hojas de
  cálculo (openpyxl), códigos de barras (python-barcode), visión artificial para escaneo
  (opencv-python) y criptografía (cryptography).
- No se requiere hardware especializado: es suficiente un equipo de oficina estándar capaz de
  ejecutar Windows y una conexión de red hacia el servidor de base de datos con fluidez.

**Para el cliente móvil:** dispositivo Android o iOS compatible con React Native y conexión de red
hacia la API del sistema.

**Para los componentes de servidor (modo multiempresa/SaaS):** entorno Linux con soporte para
contenedores Docker, base de datos MariaDB gestionada y almacenamiento de objetos compatible con
S3; despliegue documentado mediante infraestructura como código.

---

## 7. Arquitectura y estructura

Smart Manager se organiza en una arquitectura de capas con dependencia unidireccional: la interfaz
de usuario invoca a la capa de servicios, la capa de servicios invoca a la capa de acceso a datos,
y esta accede a la base de datos — la capa de presentación no contiene lógica de negocio propia,
de modo que la misma lógica se aplica de forma idéntica se acceda desde el escritorio, la API o el
cliente móvil.

**Módulos clave del repositorio:**

- `src/main.py` — punto de entrada de la aplicación de escritorio: arranca el backend interno,
  inicializa la conexión a base de datos y presenta la pantalla de inicio de sesión.
- `src/db/conexion.py` — gestor propio del pool de conexiones a la base de datos, con resolución
  automática de la empresa activa en cada consulta para el modo multiempresa.
- `src/gui/` — interfaz de escritorio, organizada en un módulo por dominio funcional (ventas,
  stock, contabilidad, recursos humanos, seguridad, etc.), sobre un conjunto de componentes
  visuales propios y reutilizables.
- `src/services/` — capa de lógica de negocio pura, organizada en más de ochenta subsistemas
  independientes (contabilidad, fiscalidad, producción, mantenimiento, calidad, seguridad,
  comercio digital, inteligencia de negocio, entre otros), sin dependencias de la interfaz gráfica
  ni del protocolo HTTP.
- `src/db/` — capa de acceso a datos, con un módulo por dominio de información.
- `src/api/routers/` — API REST, organizada en routers especializados por dominio, que expone las
  mismas operaciones de negocio al cliente móvil, al canal web propio y a futuras integraciones.
- `src/soma/` — núcleo del asistente conversacional propio.
- `src/database/migraciones/` — sistema de control de versiones del esquema de la base de datos,
  mediante migraciones numeradas y aplicadas de forma automática y ordenada en cada arranque.
- `mobile_client/` — código fuente del cliente móvil, en React Native y TypeScript.
- `assets/` — estilo visual global de la aplicación, tipografías, logotipos y ficheros de idioma.
- `infra/` — infraestructura como código para el despliegue de los componentes de servidor.

La base de datos se organiza mediante un sistema de migraciones versionadas: cada cambio en el
esquema (nueva tabla, columna o índice) se registra como un fichero numerado e independiente, con
su correspondiente función de aplicación, lo que permite reconstruir el esquema completo de forma
determinista en cualquier instalación nueva y mantener un historial íntegro de la evolución de los
datos del sistema.

---

*Fin de la Memoria Descriptiva y Justificativa del Software. Este documento describe el software
tal y como existe en el repositorio a la fecha de su redacción; no constituye asesoramiento legal —
se recomienda su revisión por un profesional de la propiedad intelectual antes de su presentación
formal ante el Registro.*
