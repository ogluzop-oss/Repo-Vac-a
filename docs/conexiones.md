# Conexiones y transacciones — Smart Manager AI (A2)

## Pool de conexiones (A2.1 — hecho)

Antes, `obtener_conexion()` abría y cerraba una conexión TCP **por cada llamada**
(312 puntos de uso). Ahora usa un **pool** (`DBUtils.PooledDB`) **detrás de la
misma API** → los 312 usos no cambian; al salir del `with`, la conexión se
**devuelve al pool** en vez de cerrarse.

- **Registro de pools por configuración** (`host/puerto/BD/usuario`): hoy un único
  pool de la BD activa; preparado para **pool‑por‑tenant** del futuro SaaS sin tocar
  la API. `obtener_conexion(config=...)` admite apuntar a otra BD/tenant.
- Parámetros (env): `DB_POOL_MAX` (máx. conexiones, 20), `DB_POOL_CACHE` (caché, 10).
  `blocking=True` (espera si se satura, no falla), `ping=1` (valida al sacar del
  pool → resistente al `wait_timeout` de MySQL), `reset=True`.
- **Degradación:** si `DBUtils` no estuviera instalado, cae a conexión directa
  (comportamiento anterior) sin romper nada.
- **Sin cambio de semántica:** A2.1 mantiene `autocommit=True`. Las transacciones
  llegan en A2.2.

Cubierto por `tests/integration/test_pool.py` (registro, reutilización, 30 hilos
concurrentes, autocommit intacto).

## Transacciones reales (A2.2 — hecho)

`transaccion()` (en `conexion.py`) abre una **transacción explícita** (`START
TRANSACTION`) sobre una conexión del pool y hace **COMMIT** al salir bien o
**ROLLBACK** ante cualquier excepción. Es **agnóstica del driver** (no usa
`autocommit()`, que el wrapper del pool no expone; sí usa `commit()`/`rollback()`,
que son DB‑API y el pool proxia). Uso: `with transaccion() as conn: with conn.cursor()…`
(no llamar a `conn.commit()` dentro).

**Corrección de concurrencia (sobreventa):** `descontar_stock` ejecuta ahora
`SELECT … FOR UPDATE` + `UPDATE` **dentro de la transacción** → el bloqueo de fila
se mantiene hasta el COMMIT. Probado: 10 hilos comprando 1 unidad de un stock de 5 →
exactamente 5 con éxito y **nunca** stock negativo.

**Operaciones migradas a `transaccion()` (prioridad económica):**
- **Ventas:** `tpv._procesar_venta` (venta + ítems + stock), `registro_venta.registrar_venta`
  (con `FOR UPDATE`), `conexion.registrar_venta_con_items` y `registrar_factura`.
- **Stock:** `descontar_stock` (FOR UPDATE efectivo).
- **Pedidos online:** `crear_pedido_online` (pedido + ítems atómicos).
- **Webhooks:** la idempotencia (`reclamar_evento`, INSERT IGNORE) ya es atómica y el
  descuento de stock que dispara el cobro usa ya `descontar_stock` transaccional;
  la transición de estado es de una sola sentencia (atómica).

Cubierto por `tests/integration/test_transacciones.py` (commit, rollback, sobreventa
concurrente, venta atómica + FOR UPDATE, pedido online atómico).

## Pendiente (A2.3 — tras tu revisión)

Migrar el resto de operaciones críticas a `transaccion()`: devoluciones, mermas,
recepciones y traspasos (estos dos últimos ya usan `begin()/rollback()` y se
alinearán con el helper).
