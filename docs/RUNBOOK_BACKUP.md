# RUNBOOK — Backup y recuperación (Smart Manager AI)

Módulo: `src/db/backup.py`. Base: MariaDB (`DB_CONFIG`). Carpeta de backups: `documentos/backups/`
(retención configurable, por defecto últimos N `.sql` + sidecar `.json` con metadatos sin secretos).

## 1. Estrategia
- **Método primario:** `mysqldump` (si está en el PATH).
- **Fallback portable:** export lógico vía PyMySQL (`_export_logico`) cuando no hay `mysqldump`.
- **Pre‑migración:** el migrador crea backup automáticamente cuando una migración declara `REQUIERE_BACKUP`.
- **Programado (M2):** `backup.backup_si_corresponde(intervalo_horas=24)` — invocar al **arrancar y/o cerrar** la app. Crea backup solo si el último supera el intervalo (diario recomendado; semanal = 168 h en un segundo punto de llamada).

## 2. Crear backup
```python
from src.db import backup
backup.crear_backup(motivo="manual")          # backup inmediato
backup.backup_si_corresponde(24)              # diario (no-op si ya hay uno reciente)
backup.backup_si_corresponde(168, motivo="semanal")
```
Salida: `{ruta, metodo, db, fecha, tablas, resultado}` + sidecar `.json`.

## 3. Verificar restaurabilidad (sin tocar producción)
```python
backup.verificar_backup()                      # restaura el último en una BD temporal y la elimina
```
Salida: `{ok, tablas, db_tmp}`. **`ok=True` ⇒ el backup es restaurable.** Ejecutar periódicamente (p.ej. tras el backup semanal).

## 4. Restauración COMPLETA (recuperación ante desastre)
1. Detener la aplicación (ningún proceso escribiendo).
2. Identificar el backup: `backup.listar_backups()` (más recientes primero).
3. Restaurar sobre la BD activa (o una nueva y repuntar `DB_NAME`):
```python
backup.restaurar_backup("documentos/backups/<archivo>.sql")
```
   Usa cliente `mysql` si está disponible; si no, PyMySQL multi‑statement.
4. Arrancar la app: el `migrador` aplicará migraciones pendientes (aditivas) si las hubiera.
5. Validar: cuadre de inventario (`reconciliacion.diagnostico`), nº de asientos, último cierre Z.

## 5. Restauración PARCIAL
- Restaurar el `.sql` en una **BD temporal** (`restaurar_backup(ruta, db="sm_tmp")`) y extraer/importar
  solo las tablas necesarias con `mysqldump`/SQL manual. Nunca sobrescribir tablas en caliente.

## 6. RPO / RTO (objetivos)
- **RPO objetivo:** ≤ 24 h con backup diario programado (≤ 1 h si se programa intradía).
- **RTO objetivo:** minutos (mysqldump) a < 1 h según volumen.
- **Integridad:** los asientos y Verifactu llevan hash encadenado → tras restaurar, verificar continuidad de hash y reconciliar (`src/db/reconciliacion.py`).

## 7. Buenas prácticas
- Copiar los `.sql` fuera de la máquina (almacenamiento externo/nube) — la retención local no es DR.
- Probar `verificar_backup()` regularmente (un backup no verificado no es un backup).
- No incluir secretos en nombres/metadatos (ya garantizado por el módulo).
