"""
Migración 0357 — Reseñas de clientes + comentarios (petición explícita, 2026-11-22). NUEVAS
tablas, aditivas, reversibles.

Viven en la base COMPARTIDA (igual que `cuentas_web_central`/`altas_web_stripe`): una reseña es
sobre el PRODUCTO Smart Manager en general, no un dato de negocio de un tenant — y además tiene
que poder listarse/mostrarse en la home pública sin depender de a qué base física pertenece cada
empresa. `id_empresa` referencia el `id_empresa_central` ya usado por `cuentas_web_central`/
`altas_web_stripe` (no hay FK entre bases distintas por diseño — mismo criterio ya usado ahí).

Una reseña por empresa (clave única `id_empresa` en `resenas_sitio`): se edita/sustituye la
existente en vez de acumular varias — igual que la mayoría de plataformas de reseñas de software
(una opinión por cuenta, editable). Los comentarios sí son multiples por reseña y por autor.
"""

VERSION = "0357"
DESCRIPCION = "Tablas resenas_sitio y resenas_sitio_comentarios — reseñas de clientes y comentarios"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS resenas_sitio (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(36) NOT NULL,
            nombre_mostrado VARCHAR(255) NOT NULL,
            puntuacion TINYINT NOT NULL,
            texto TEXT NOT NULL,
            creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_resena_empresa (id_empresa),
            INDEX idx_resena_creado (creado_en)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS resenas_sitio_comentarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_resena INT NOT NULL,
            id_empresa VARCHAR(36) NOT NULL,
            nombre_mostrado VARCHAR(255) NOT NULL,
            texto TEXT NOT NULL,
            creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_comentario_resena (id_resena, creado_en)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS resenas_sitio_comentarios")
    cur.execute("DROP TABLE IF EXISTS resenas_sitio")
