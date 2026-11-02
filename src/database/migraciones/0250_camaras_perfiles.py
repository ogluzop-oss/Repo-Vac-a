"""
Migración 0250 — Videovigilancia: perfiles dual-stream (mainstream/substream) por ONVIF. ADITIVA,
idempotente, reversible.

`camaras.fuente`/`fuente_cifrada` (migración 0176) siguen siendo la URL de respaldo (compatibilidad
total con cámaras dadas de alta manualmente o antes de esta capacidad). Se añaden 2 perfiles NUEVOS y
OPCIONALES, protegidos con el MISMO mecanismo de cifrado (Fernet vía Secret Manager, jamás en claro):
`fuente_main`/`fuente_main_cifrada` (alta resolución, grabación 24/7 y vivo en pantalla completa) y
`fuente_sub`/`fuente_sub_cifrada` (baja resolución, vivo en la rejilla — menor CPU/ancho de banda). Una
cámara sin estos perfiles (NULL) sigue funcionando exactamente igual que hoy: `registro.fuente_para`
resuelve en cascada hacia `fuente`/`fuente_cifrada`.
"""

VERSION = "0250"
DESCRIPCION = "Videovigilancia: perfiles dual-stream ONVIF (camaras.fuente_main/fuente_sub, cifrados)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE camaras ADD COLUMN IF NOT EXISTS fuente_main VARCHAR(255) DEFAULT NULL")
    cur.execute("ALTER TABLE camaras ADD COLUMN IF NOT EXISTS fuente_main_cifrada TEXT DEFAULT NULL")
    cur.execute("ALTER TABLE camaras ADD COLUMN IF NOT EXISTS fuente_sub VARCHAR(255) DEFAULT NULL")
    cur.execute("ALTER TABLE camaras ADD COLUMN IF NOT EXISTS fuente_sub_cifrada TEXT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE camaras DROP COLUMN IF EXISTS fuente_sub_cifrada")
    cur.execute("ALTER TABLE camaras DROP COLUMN IF EXISTS fuente_sub")
    cur.execute("ALTER TABLE camaras DROP COLUMN IF EXISTS fuente_main_cifrada")
    cur.execute("ALTER TABLE camaras DROP COLUMN IF EXISTS fuente_main")
