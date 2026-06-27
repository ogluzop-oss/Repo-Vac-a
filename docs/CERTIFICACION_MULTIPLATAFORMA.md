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
