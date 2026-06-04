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

### AI Forecasting

`src/gui/informe_reposicion.py` calls `predecir_ventas_semanales()` using Facebook Prophet. It also calls `verificar_ia_reposicion()` to raise smart stock alerts. Prophet is an optional dependency; the app degrades gracefully if unavailable.

### RFID Integration

`src/utils/rfid_gateway.py` communicates with Zebra RFID readers over HTTP. `src/utils/rfid_worker.py` wraps this in a QThread. A simulated mode is available when hardware is absent.

## Output Files

Generated PDFs, labels, tickets, and reports are written to subdirectories under `documentos/` (albaranes, etiquetas, facturación, informes de reposición, QR ubicaciones, stocks, tickets).
