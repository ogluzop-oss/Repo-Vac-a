# Smart Manager AI

Aplicación de escritorio (Windows · PyQt6) para **gestión integral de almacén y retail**:
recepción de palés, mapa de ubicaciones en tienda, control de stock, TPV/ventas,
etiquetas de precio, gestión de mermas, fichajes y horarios, documentación
fiscal/laboral, y **previsión de demanda con IA**.

Interfaz **multiidioma (20 lenguas)** con cambio en caliente, asistente de voz
**SOMA**, y generación de documentos (tickets, albaranes, contratos, nóminas,
certificados) en PDF.

---

## Requisitos

- **Python 3.11+** (probado con 3.13)
- **MariaDB / MySQL** en ejecución
- Windows (algunas integraciones de hardware/voz son específicas de Windows)

## Instalación

```bash
# 1. Dependencias
pip install -r requirements.txt

# 2. Configuración: copia la plantilla y rellénala
copy .env.example .env        # Windows
#   cp .env.example .env       (Linux/Mac)
```

Edita `.env` con tus credenciales de base de datos (mínimo `DB_HOST`, `DB_USER`,
`DB_PASSWORD`, `DB_NAME`, `DB_PORT`). Las tablas se crean automáticamente en el
primer arranque desde `src/database/bootstrap_mariadb.sql`.

## Ejecución

```bash
python src/main.py
```

---

## Arquitectura

```
src/main.py          Punto de entrada — SmartManagerApp (QStackedWidget)
src/gui/             Pantallas de la interfaz (login, menús, módulos)
src/db/              Capa de datos (conexion.py + módulos por dominio)
src/utils/           Utilidades compartidas (RFID, impresión, i18n, IA, voz…)
src/database/        SQL de arranque y datos de ejemplo
assets/              Estilo global, fuentes, logos, traducciones (assets/lang/)
documentos/          Salida en tiempo de ejecución (PDF, etiquetas, informes…)
```

- **Roles**: `ADMINISTRADOR`, `GERENTE`, `OPERARIO` (controlan qué módulos se ven).
- **Sin ORM**: consultas directas con PyMySQL y pool de conexiones.
- **Hilos**: trabajos pesados (RFID, búsquedas, importación) en `QThread`; la UI
  se actualiza solo vía señales/slots.

## Internacionalización (i18n)

- 20 idiomas; selector en el login; **cambio de idioma en caliente** sin reiniciar.
- **Nivel 1** (instantáneo): textos fijos en `assets/lang/<código>.json`, vía
  `i18n.tr("seccion.clave")`. Cadena de respaldo: idioma actual → inglés → defecto.
- **Nivel 2** (IA): contenido dinámico (documentos, SOMA) vía `src/utils/ai_translator.py`.
- **Backfill de traducciones**: rellena los idiomas que falten desde el español.

  ```bash
  # requiere ANTHROPIC_API_KEY en .env (+ pip install anthropic)
  python backfill_idiomas.py --dry-run      # informe
  python backfill_idiomas.py fr de it pt    # idiomas concretos
  python backfill_idiomas.py                # los 20 idiomas
  ```

- **PDF multiescritura**: `src/utils/pdf_fonts.py` registra automáticamente una
  fuente Unicode del sistema (CJK/árabe/cirílico…) cuando el idioma lo requiere,
  con respaldo a Helvetica.

## Configuración (.env)

| Variable | Obligatoria | Descripción |
|---|---|---|
| `DB_HOST` `DB_USER` `DB_PASSWORD` `DB_NAME` `DB_PORT` | Sí | Conexión MariaDB/MySQL |
| `ANTHROPIC_API_KEY` | No | Traducción IA dinámica + backfill |
| `SMART_MANAGER_TRANSLATE_MODEL` | No | Modelo de traducción (def. `claude-haiku-4-5-20251001`) |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` | No | Envío de albaranes/informes por email |

Consulta `.env.example` para la plantilla completa.

## Dependencias opcionales

La app **degrada con elegancia** si faltan dependencias no esenciales:
IA (`anthropic`, `prophet`, `matplotlib`), voz (`edge-tts`, `pyttsx3`,
`SpeechRecognition`, `pygame`) y hardware (`opencv-python`, `pyzbar`, `pyserial`,
`pyusb`, `python-escpos`). Ver `requirements.txt` para el detalle por grupos.
