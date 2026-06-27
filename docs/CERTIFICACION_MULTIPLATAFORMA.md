# Certificación multiplataforma — Smart Manager AI (Bloque 8)

> **Fecha:** 2026-06-27 · **Alcance:** compatibilidad, despliegue, hardware, UX, rendimiento.
> **Regla aplicada:** *no asumir compatibilidad; demostrarla con evidencia*. Cuando no hay
> evidencia ejecutable, se declara honestamente **NO VERIFICADO** en lugar de afirmar PASS.

## 0. Honestidad metodológica (entorno de certificación)

Esta auditoría se ejecutó en **una única máquina Windows 10 Pro x64**, sin acceso a:
macOS, Linux, Android, iOS, ARM64, ni hardware físico (PDAs Zebra/Honeywell/Datalogic/
Newland/Sunmi/Bluebird/Chainway, impresoras EPSON/Bixolon/Star, pantallas táctiles 10–22").

En consecuencia, este documento distingue tres niveles de evidencia:

- **✅ VERIFICADO** — ejecutado y medido en este host (Windows x64) o test determinista.
- **🟡 ANÁLISIS ESTÁTICO** — revisado en el código; portable por diseño, pendiente de ejecución real.
- **⛔ NO VERIFICADO** — requiere SO/hardware/CI no disponibles aquí; no se certifica.

---

## FASE A — Auditoría de dependencias de plataforma (✅ realizada)

Inventario obtenido con búsquedas sobre el código (`git grep`).

### Resultados

| Aspecto | Resultado | Evidencia |
|---|---|---|
| Rutas absolutas con letra de unidad (`C:\…`) | **Ninguna** en código real | falsos positivos = `\n` en strings y URLs `https://` |
| Imports Windows-only (`win32`, `winreg`, `pywintypes`, `windll`) | **Ninguno** | sin atadura a pywin32 |
| Detección de SO existente | Presente | `platform.system()` / `os.name` en `utils/config.py`, `utils/perifericos.py`, varias GUIs |
| `os.startfile` (solo Windows) | **~10 usos** en GUIs | centro_documental, etiquetas_precios, gestion_mermas, gestion_usuarios, informe_reposicion, portal_empleado, recepcion_pale |
| Apertura por shell no portable | `os.system(f'start/open/xdg-open …')` | `ubicacion_tienda.py` (no portable + riesgo de inyección) |
| `subprocess` Popen open/xdg-open | recepcion_pale, ventas, tpv (ya con ramas SO) | parcialmente portable |
| Backup BD | `subprocess.run` de `mysqldump`/`mysql` | portable si los binarios están en PATH |
| Impresión | `QPrinter` (Qt, multiplataforma) + ESC/POS USB (`escpos`) | `rrhh/gui/horarios.py`, `utils/impresion.py`, `utils/perifericos.py` |
| Báscula / serie | `pyserial` | `services/tpv/scale_service.py` |
| Dependencias del `requirements.txt` | `pyserial`, `pyusb` (**multiplataforma**); sin `pywin32` | línea 50–51 |

### Diagnóstico

- **No hay bloqueos duros de portabilidad** (sin pywin32, sin rutas absolutas, sin registro de Windows).
- El principal foco de no-portabilidad es la **apertura/impresión de ficheros** dispersa e
  inconsistente entre módulos (algunos solo Windows, otros con ramas SO duplicadas).
- El acceso a hardware (USB/serie) usa librerías multiplataforma, pero **drivers y permisos
  difieren por SO** (p. ej. acceso USB sin privilegios en Linux requiere reglas `udev`).

---

## Correcciones aplicadas en este bloque (✅ verificadas en Windows + tests)

| Cambio | Descripción | Evidencia |
|---|---|---|
| `src/utils/plataforma.py` | Capa portable única: `abrir_archivo`, `abrir_carpeta`, `imprimir_archivo` (Windows/macOS/Linux), degradable sin romper UI | 8 tests |
| `src/utils/perfil_tactil.py` | Perfil táctil global Normal/Táctil/TPV/PDA con mínimos 48/56/44 px | 3 tests |
| `src/services/perifericos/escaner_universal.py` | Capa universal de lectura (keyboard-wedge HID portable; parser por temporización) | 5 tests |
| `src/gui/ubicacion_tienda.py` | Migrado `os.system(f'…')` → `plataforma.abrir_carpeta` (portable, sin shell) | suite en verde + import OK |

> Pendiente recomendado (no aplicado para minimizar superficie de cambio): migrar los ~10
> `os.startfile` restantes a `plataforma.abrir_archivo`/`imprimir_archivo`. Es mecánico y de bajo riesgo.

---

## FASE B — Windows (✅ x64 / ⛔ ARM64)

| Ítem | Estado | Evidencia |
|---|---|---|
| Windows 10 x64 | ✅ VERIFICADO | host de ejecución; suite 894 tests OK |
| Arranque Qt/QApplication | ✅ 102 ms | benchmark |
| Import TPV | ✅ 469 ms | benchmark |
| Import editor ubicación | ✅ 1193 ms (módulo más pesado) | benchmark |
| Import dashboards (CRM/BI) | ✅ 2–8 ms | benchmark |
| Windows 11 | 🟡 ANÁLISIS ESTÁTICO | misma API Qt6/Python; sin host Win11 para medir |
| Windows ARM64 | ⛔ NO VERIFICADO | sin host ARM64 |
| Uso RAM/CPU | ⛔ no medido | falta `psutil` en el intérprete (instalar para medir RSS) |

---

## FASE C — macOS · FASE D — Linux

⛔ **NO VERIFICADO** (sin hosts). Análisis estático: el código es portable por diseño
(PyQt6, reportlab, openpyxl, pandas son multiplataforma; apertura/impresión ya encapsuladas).
Riesgos a validar en host real: permisos de sistema en macOS (acceso a archivos/impresión),
reglas `udev` en Linux para USB, disponibilidad de `lpr`/CUPS y `xdg-open`.

---

## FASE E — Tablet · FASE F — TPV táctil · FASE M — Modo táctil

| Ítem | Estado | Notas |
|---|---|---|
| Escalado responsive / High-DPI | ✅ base verificada | `main.py` PassThrough; fase responsive previa (ver `project_responsive_tracking`) |
| Perfil táctil (48/56/44 px, modos) | ✅ módulo + tests | integración visual en widgets/estilos: 🟡 pendiente cableado UI |
| Táctil real / rotación / gestos | ⛔ NO VERIFICADO | requiere dispositivos físicos |

---

## FASE G — PDA/MDE · FASE H — Escáneres · FASE I — Impresoras

| Ítem | Estado | Notas |
|---|---|---|
| Capa universal de escáner (wedge HID) | ✅ núcleo + tests | portable a todo SO sin drivers; falta event-filter en TPV (🟡) |
| Escáner serie/USB (Zebra/Honeywell/…) | 🟡 abstracción presente | `utils/perifericos.escanear_codigo`; sin hardware para certificar |
| Impresoras EPSON/Bixolon/Star (USB/red/BT) | 🟡 vía QPrinter + ESC/POS | sin hardware para certificar tickets/facturas/devoluciones |
| PDA Zebra/Honeywell/Datalogic/Newland/Sunmi/Bluebird/Chainway | ⛔ NO VERIFICADO | requiere los terminales físicos |

---

## FASE J — Android · FASE K — iOS

⛔ **NO VERIFICADO / limitación tecnológica conocida.** PyQt6 **no** dispone de un camino de
empaquetado nativo soportado y estable para Android/iOS (Qt for Python no ofrece despliegue
móvil de primera clase como Qt C++). Opciones reales a evaluar como proyecto aparte:

- **Acceso remoto** (la app de escritorio servida vía RDP/VNC/navegador) — más rápido.
- **Cliente móvil dedicado** consumiendo la API backend (`src/backend`) — recomendado a medio plazo.
- Reescritura de UI móvil (Qt C++/Flutter/web) — alto coste.

No se certifica ejecución nativa Android/iOS; se documenta el grado real (no soportado nativamente hoy).

---

## FASE L — Rendimiento (✅ Windows x64)

| Métrica | Valor (Windows x64) |
|---|---|
| Init Qt/QApplication | 102 ms |
| Import módulo TPV | 469 ms |
| Import editor ubicación tienda | 1193 ms |
| Import dashboards (CRM/BI corp) | 2–8 ms |
| Coste de los módulos nuevos del Bloque 8 | 1–4 ms (despreciable) |
| Suite de pruebas | 894 passed / 0 fail |

Otras plataformas: ⛔ no medible aquí. RAM/CPU: pendiente (`psutil`).

---

## FASE N — Offline (🟡)

Integración con Bloque 7 (offline-first/SQLite/sync) presente y con suite en verde en este host.
Certificación de sincronización/recuperación **por plataforma** ⛔ requiere los SO destino.

---

## FASE O — Instaladores (🟡 especificación, sin build)

| Plataforma | Formato | Estado |
|---|---|---|
| Windows | EXE / MSI | 🟡 vía PyInstaller (+ Inno Setup/WiX); sin build verificado aún |
| macOS | DMG | ⛔ requiere host macOS para `py2app`/PyInstaller |
| Linux | DEB / RPM | ⛔ requiere host Linux para empaquetar |
| Android | APK | ⛔ no soportado por el stack actual (ver Fase J) |

---

## FASE P — Informe de certificación (resumen)

### Compatibles (✅ verificado)
- **Windows 10 x64** (host): arranque, imports, suite completa, módulos nuevos.

### Compatibles con observaciones (🟡 portable por diseño / pendiente ejecución real)
- Windows 11, macOS (Intel/Apple Silicon), Linux (Ubuntu/Debian/Rocky): código portable;
  falta ejecución en host real.
- TPV táctil y tablets: base responsive + perfil táctil listos; falta cableado UI y dispositivo.
- Escáneres (wedge) e impresoras (QPrinter/ESC-POS): abstracción lista; falta hardware.

### No compatibles / no verificables aquí (⛔)
- Windows ARM64, Android/iOS nativo (limitación del stack), PDAs/MDE físicos.

### Riesgos detectados
1. `~10 os.startfile` Windows-only aún sin migrar (degradan en otros SO).
2. Acceso USB/serie depende de permisos por SO (udev en Linux, firma/permize en macOS).
3. Empaquetado móvil nativo no soportado por PyQt6.
4. RAM/CPU no medidos (falta `psutil`).

### Pendientes
- Migrar los `os.startfile` restantes a `plataforma.*`.
- Cablear `perfil_tactil` en estilos/widgets y un selector en Configuración.
- Integrar `escaner_universal` como event-filter del TPV.
- CI multi-OS (GitHub Actions matrix: windows/macos/ubuntu) para evidencia reproducible.
- Hosts/dispositivos reales para Fases C, D, E, F, G, I, N por plataforma.

### Porcentaje de certificación por plataforma (honesto)

| Plataforma | % | Base |
|---|---|---|
| Windows (x64) | **90%** | verificado en host (falta empaquetado/medición RAM) |
| Windows (ARM64) | **20%** | solo análisis estático |
| macOS | **35%** | portable por diseño, sin host |
| Linux | **40%** | portable por diseño, sin host |
| Tablet (Win/Android/iPad) | **30%** | responsive + perfil táctil, sin dispositivo |
| TPV táctil | **45%** | responsive + perfil táctil + abstracciones, sin pantalla |
| PDA | **25%** | wedge universal listo, sin terminal |
| MDE | **25%** | igual que PDA |
| Android | **10%** | sin camino nativo (vía API/remoto) |
| iOS | **10%** | sin camino nativo (vía API/remoto) |

> Estimaciones cualitativas basadas en el nivel de evidencia real, no en suposiciones.

---

## Conclusión

Smart Manager AI es **portable por diseño** (sin ataduras duras a Windows) y queda
**certificado en Windows x64** con evidencia. Para una certificación multiplataforma plena se
requiere ejecutar las fases pendientes en **hosts reales y/o CI multi-OS** y con **hardware**
de cada categoría. Este bloque deja además la base de portabilidad (`plataforma`,
`perfil_tactil`, `escaner_universal`) verificada y sin tocar lógica de negocio.

---

# Bloques 8.1 – 8.4 — Avance verificable (2026-06-27)

## Entregable 1 — Informe CI Multi-OS

Workflow nuevo `.github/workflows/multiplataforma.yml` (matrix **ubuntu/windows/macos × Python 3.12/3.13**).
Genera evidencia objetiva en cada push (no depende de MariaDB; la suite con BD sigue en `ci.yml`):
instalación de dependencias, `compileall src`, init de Qt (offscreen), imports de ventanas clave,
tests portables del Bloque 8, y registro de SO/Python/Qt/duración en el *step summary*.
Principio aplicado: **no se marca PASS si el paso no se ejecutó** (cada paso falla en rojo si falla).

> Estado: workflow **válido** (YAML verificado) y listo. La evidencia por SO se materializa al
> hacer push a GitHub (Linux/Windows/macOS reales del runner). No se declara PASS hasta que el run exista.

## Entregable 2 — Informe de Portabilidad (dependencias eliminadas)

Migración **completa** de aperturas/impresiones a la capa única `src/utils/plataforma.py`:

| Antes (no portable / disperso) | Después |
|---|---|
| `os.startfile(...)` ×20 en 11 GUIs | `plataforma.abrir_archivo` / `abrir_carpeta` / `imprimir_archivo` |
| `os.system(f'start/open/xdg-open …')` (ubicacion_tienda) | `plataforma.abrir_carpeta` (sin shell, sin inyección) |
| 4 bloques `if platform.system()==... subprocess.Popen([...])` (recepcion_pale, tpv, ventas ×2) | una sola llamada portable |

Auditoría post-migración (`git grep`): **0** `os.startfile`, **0** `os.system`, **0** `Popen(["open"/"xdg-open"])`
fuera de `plataforma.py`. Sin `pywin32`/`winreg`. Tests específicos (apertura/impresión Win/mac/Linux,
degradación sin `xdg-open`/`lpr`). Suite completa en verde (sin romper impresión/exportación/apertura).

## Entregable 3 — Informe TPV Táctil (perfiles aplicados)

- `src/utils/perfil_tactil.py`: perfiles **NORMAL / TACTIL / TPV / PDA** (mín. 0/48/56/44 px) + espaciado.
- Integrado en el QSS global (`assets/estilo_global._qss_tactil`): en perfil táctil aumenta automáticamente
  **botones, inputs, combos, spinboxes, date-edits, filas de tabla, cabeceras y pestañas**. En NORMAL no
  cambia nada (overlay vacío → comportamiento idéntico al actual). Configurable por
  `SMART_MANAGER_PERFIL_TACTIL` o `perfil_tactil.set_perfil()`.
- Objetivo cumplido a nivel de estilos: controles operables con dedo/guantes en pantallas industriales.
- Pendiente (no bloqueante): selector de perfil en Configuración persistido en `preferencias_usuario`.

## Entregable 4 — Informe Escáner Universal (módulos integrados)

- Núcleo portable `escaner_universal.BufferEscaner` (wedge HID por temporización) + integración Qt
  `src/gui/escaner_qt.FiltroEscaner` / `instalar_escaner()` (event-filter **no intrusivo**: observa, no
  bloquea el tecleo; soporta Keyboard-Wedge, USB HID y Bluetooth HID de cualquier fabricante —
  Zebra/Honeywell/Datalogic/Newland/Sunmi/Bluebird/Chainway).
- **Integrado en el TPV**: captura global de escaneo aunque el campo SKU no tenga el foco, sin doble alta.
- **Resto de módulos** (Smart Stock, Recepciones, Inventarios, Traspasos, Almacenes, Mermas, Reposición):
  ya aceptan lectura wedge por sus campos de código existentes (wedge = teclado, portable). Adopción del
  filtro global = **1 línea** (`instalar_escaner(self, handler)`) cuando se quiera captura sin foco.
- Tests: emisión por ráfaga+terminador, no-consumo por defecto, conexión de callback.

## Entregable 5 — Informe Hardware

| Categoría | Estado | Detalle |
|---|---|---|
| Impresoras EPSON/Bixolon/Star/Sunmi (USB/Bluetooth/TCP-IP) | **PREPARADO PARA VALIDACIÓN** | `services/perifericos/impresora.py`: config + adaptadores ESC/POS (Usb/Network/Serial), validación y degradación sin hardware; tests |
| TPV táctil 10"/15"/17"/22" | **PREPARADO** | perfil táctil + responsive; falta pantalla física |
| PDA/MDE Zebra/Honeywell/Datalogic/Newland/Sunmi | **PREPARADO** | escáner wedge universal + teclado físico (HID); falta terminal físico |
| Cualquier categoría sin dispositivo | **NO CERTIFICADO** | se clasifica como PREPARADO, nunca como certificado |

Adaptadores existentes: ESC/POS (impresión), wedge/serie/USB (escáner), pyserial (báscula). Dependencias
pendientes para validación real: el hardware físico + (en Linux) reglas `udev` para USB.

## Entregable 6 — Porcentaje de certificación actualizado

| Plataforma | Antes (8.0) | Ahora (8.1–8.4) | Motivo |
|---|---|---|---|
| Windows x64 | 90% | **92%** | portabilidad total + escáner/táctil integrados y testeados |
| Linux | 40% | **55%** | CI multi-OS preparado + portabilidad total (evidencia al primer run verde) |
| macOS | 35% | **50%** | íd. Linux |
| Windows ARM64 | 20% | **25%** | portabilidad total (sigue sin host ARM64) |
| TPV táctil | 45% | **65%** | perfil táctil aplicado en QSS + escáner integrado |
| Tablet | 30% | **40%** | perfil táctil + responsive |
| PDA | 25% | **45%** | escáner wedge universal integrado |
| MDE | 25% | **45%** | íd. PDA |
| Android | 10% | **10%** | sin cambio (sin camino nativo PyQt6) |
| iOS | 10% | **10%** | sin cambio |

> Los % de Linux/macOS son "preparado, pendiente de primer run CI verde": subirán a evidencia real
> en cuanto el workflow se ejecute en GitHub. No se declara compatibilidad sin ese run.

## Evidencia de no-regresión (este host, Windows x64)

- Suite completa: **906 passed / 0 fail** (879 base + 27 nuevos del Bloque 8).
- 0 llamadas no portables fuera de `plataforma.py`. Sintaxis OK en los 11 GUIs migrados.
