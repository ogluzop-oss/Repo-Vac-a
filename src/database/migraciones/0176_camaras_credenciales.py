"""
Migración 0176 — Videovigilancia: cifra las credenciales RTSP de las cámaras. ADITIVA, reversible.

Hasta ahora `camaras.fuente` guardaba la URL completa (rtsp://usuario:contraseña@ip/…) EN CLARO, violando la
regla del proyecto (jamás secretos en claro). Se añade `fuente_cifrada` (TEXT): la URL con credenciales se
cifra con el Secret Manager (Fernet) y en `fuente` queda una versión ENMASCARADA (sin contraseña). El grabador
descifra la URL real solo en el momento de conectar (`registro.fuente_efectiva`). Las filas existentes con
credenciales en claro se migran (cifrar + enmascarar) en el mismo paso, best-effort.

Nota: `revertir` elimina la columna cifrada; como `fuente` ya está enmascarada, tras revertir habría que
re-introducir las contraseñas (no se conservan en claro por diseño).
"""

VERSION = "0176"
DESCRIPCION = "Videovigilancia: cifra credenciales RTSP (camaras.fuente_cifrada) + enmascara fuente"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE camaras ADD COLUMN IF NOT EXISTS fuente_cifrada TEXT DEFAULT NULL")
    # Migrar filas existentes con credenciales en claro (rtsp://user:pass@host): cifrar + enmascarar.
    try:
        from src.services.camaras.registro import _enmascarar, _tiene_credenciales
        from src.services.seguridad import secret_manager
        cur.execute("SELECT id, fuente FROM camaras WHERE fuente LIKE '%://%:%@%'")
        for row in cur.fetchall():
            cid = row[0] if not isinstance(row, dict) else row["id"]
            url = row[1] if not isinstance(row, dict) else row["fuente"]
            if not _tiene_credenciales(url):
                continue
            cif = secret_manager.cifrar(url)
            if cif:
                cur.execute("UPDATE camaras SET fuente=%s, fuente_cifrada=%s WHERE id=%s",
                            (_enmascarar(url), cif, cid))
    except Exception:
        # Sin Secret Manager disponible al migrar: la columna queda creada; las credenciales antiguas se
        # protegen en el próximo alta/edición de la cámara. No se bloquea la migración.
        pass


def revertir(cur):
    cur.execute("ALTER TABLE camaras DROP COLUMN IF EXISTS fuente_cifrada")
