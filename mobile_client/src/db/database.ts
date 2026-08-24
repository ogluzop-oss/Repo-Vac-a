/**
 * Base de datos local SQLite del dispositivo (offline-first).
 *
 * Materializa lo que `src/services/mobile/sync.py` describe como "el contrato en el dispositivo
 * (SQLite local en la app nativa)". Aquí vive la tabla `outbox` (cola de operaciones creadas sin
 * conexión) que en el servidor solo estaba modelada en memoria.
 */
import SQLite, {
  type SQLiteDatabase,
  type ResultSet,
} from 'react-native-sqlite-storage';

SQLite.enablePromise(true);
SQLite.DEBUG(false);

const DB_NAME = 'smartmanager.db';

let _db: SQLiteDatabase | null = null;

const SCHEMA = `
CREATE TABLE IF NOT EXISTS outbox (
  id          TEXT PRIMARY KEY NOT NULL,
  entidad     TEXT NOT NULL,
  operacion   TEXT NOT NULL,
  datos       TEXT NOT NULL,           -- JSON serializado
  idem        TEXT NOT NULL,           -- clave de idempotencia
  ts          REAL NOT NULL,           -- epoch (segundos)
  estado      TEXT NOT NULL DEFAULT 'pendiente'  -- pendiente|sincronizado|fallido
);
CREATE INDEX IF NOT EXISTS idx_outbox_estado ON outbox (estado);
`;

/** Abre (una sola vez) la base de datos y garantiza el esquema. */
export async function getDatabase(): Promise<SQLiteDatabase> {
  if (_db) {
    return _db;
  }
  const db = await SQLite.openDatabase({name: DB_NAME, location: 'default'});
  // executeSql no admite varias sentencias en algunas plataformas → dividir por ';'.
  for (const stmt of SCHEMA.split(';').map(s => s.trim()).filter(Boolean)) {
    await db.executeSql(stmt);
  }
  _db = db;
  return db;
}

/** Ejecuta una sentencia y devuelve el ResultSet crudo. */
export async function exec(
  sql: string,
  params: unknown[] = [],
): Promise<ResultSet> {
  const db = await getDatabase();
  const [res] = await db.executeSql(sql, params);
  return res;
}

/** Cierra la base (p. ej. en tests). */
export async function closeDatabase(): Promise<void> {
  if (_db) {
    await _db.close();
    _db = null;
  }
}
