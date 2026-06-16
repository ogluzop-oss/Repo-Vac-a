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

## Pendiente

- **A2.2:** context manager `transaccion()` (autocommit off scoped, commit/rollback)
  + arreglo de `descontar_stock` (FOR UPDATE efectivo dentro de transacción).
- **A2.3:** migrar operaciones críticas (ventas, stock, pedidos online, webhooks,
  devoluciones, mermas, recepciones, traspasos) a `transaccion()`.

## Hallazgo a corregir en A2.2 (registrado)

Con `autocommit=True`, los `conn.commit()` actuales son no‑ops y el
`SELECT … FOR UPDATE` de `descontar_stock` **no mantiene el bloqueo** (se libera al
terminar el SELECT) → riesgo de **sobreventa** en concurrencia. Se corrige en A2.2
ejecutando SELECT FOR UPDATE + UPDATE dentro de una misma transacción.
