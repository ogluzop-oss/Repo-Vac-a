# Migraciones versionadas — Smart Manager AI (C4)

Motor propio, numerado, **preparado para SaaS** (multi-tenant por conexión).
Prioriza la **seguridad del dato** sobre la velocidad: backup automático previo.

## Conceptos

- **Migración** = módulo Python `src/database/migraciones/NNNN_descripcion.py` con:
  `VERSION` (`"0002"`), `DESCRIPCION`, `aplicar(cur)` y opcional `revertir(cur)`
  (+ `REVERSIBLE`, `REQUIERE_BACKUP`).
- **Registro/auditoría** en `schema_migraciones`: versión, descripción, checksum,
  fecha, **duración (ms)**, **ejecutor/proceso**, **tenant**, resultado
  (`ok`/`stamp`/`error`).
- **Baseline 0001** envuelve `ensure_schema()` (idempotente). En instalaciones ya
  desplegadas se **sella** (stamp) sin re-ejecutar nada destructivo.

## Cómo añadir una migración

1. Crea `src/database/migraciones/0002_mi_cambio.py`:
   ```python
   VERSION = "0002"
   DESCRIPCION = "Añade índice X"
   def aplicar(cur):
       cur.execute("ALTER TABLE articulos ADD INDEX IF NOT EXISTS idx_x (categoria)")
   def revertir(cur):
       cur.execute("ALTER TABLE articulos DROP INDEX IF EXISTS idx_x")
   ```
2. **Añádela a `MODULOS`** en `src/database/migraciones/__init__.py` (garantiza el
   descubrimiento dentro del `.exe`).
3. Reglas: idempotente cuando sea posible; **NUNCA** secretos/credenciales (usar el
   sistema de claves de C1); datos en lotes para evitar locks; `ALGORITHM=INSTANT`
   al añadir columnas en tablas grandes.

## API del runner (`src/db/migrador.py`)

- `estado(conexion_fn=None)` → estado de cada migración.
- `aplicar_pendientes(conexion_fn=None, backup=True)` → backup previo + aplica
  pendientes en orden; sella la baseline en BD existentes; se detiene ante error.
- `sellar(version, conexion_fn=None)` → marca como aplicadas hasta `version`.
- `revertir(version_objetivo, conexion_fn=None)` → downgrade con `revertir()`.

**SaaS / multi-tenant:** todas las operaciones aceptan `conexion_fn` (fábrica de
conexión) → ejecutables por cada base/tenant de forma independiente y desde
procesos de despliegue. El registro `schema_migraciones` (con columna `tenant`)
queda en cada base.

## Backups (`src/db/backup.py`)

- `mysqldump` (1ª opción; contraseña por `MYSQL_PWD`, nunca en línea de comandos);
  si no está, **export lógico** (CREATE+INSERT). Sidecar JSON con metadatos
  (fecha, versión objetivo, base, método, tablas, resultado). **Retención**
  configurable (`MIGRACIONES_BACKUP_RETENCION`, por defecto 10) en
  `documentos/backups/`.

## Limitación importante (DDL no transaccional)

En MariaDB el DDL hace COMMIT implícito: una migración a medias **no se deshace
sola**. Por eso: migraciones atómicas, `revertir()` explícito y **backup previo**
como red de seguridad real.

## Integración en el arranque

`init_db()` (llamado en `main.py` al arrancar) ahora: 1) ejecuta `ensure_schema()`
(idempotente, como siempre); 2) llama al runner (`aplicar_pendientes`), que sella la
baseline en instalaciones existentes y aplica las migraciones nuevas (0002+) con
backup previo. Si el runner fallara, el esquema base ya quedó garantizado.

## CLI (automatización de despliegues)

```bash
python -m src.db.migrador estado          # lista versiones y si están aplicadas
python -m src.db.migrador aplicar         # aplica pendientes (con backup previo)
python -m src.db.migrador aplicar --sin-backup
python -m src.db.migrador sellar 0001     # marca como aplicadas hasta una versión
python -m src.db.migrador revertir 0001   # downgrade hasta la versión indicada
```

(Respeta `DB_*`/`TEST_DB_NAME` del entorno → ejecutable por tenant en despliegues SaaS.)

## Estado de implementación
- **C4 completado:** runner + auditoría + baseline + sellado + backup con retención +
  integración en el arranque + downgrade/revertir + CLI. Documentado y con pruebas.
