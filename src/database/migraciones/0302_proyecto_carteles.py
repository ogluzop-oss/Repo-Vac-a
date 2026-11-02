"""
Migración 0302 — Carteles/Folletos publicitarios (4ª pestaña del módulo Proyectos). ADITIVA.

`proyecto_carteles`: un diseño de cartel/folleto ligado a un proyecto (`id_proyecto`, FK aplicativa
igual que `proyecto_tareas`/`proyecto_horas`/`proyecto_costes`, sin FK real). El lienzo se guarda
como modelo de contenido serializado (`contenido_json`) — el mismo que lee/escribe el editor
interactivo (`gui/proyectos_carteles_gui.py`) y el renderizador headless
(`services/proyectos/render_cartel.py`).
"""

VERSION = "0302"
DESCRIPCION = "Proyectos: proyecto_carteles (editor de carteles/folletos publicitarios)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS proyecto_carteles (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa      VARCHAR(36)  DEFAULT NULL,
            id_proyecto     INT          NOT NULL,
            titulo          VARCHAR(160) NOT NULL DEFAULT 'Sin título',
            tipo            VARCHAR(20)  NOT NULL DEFAULT 'cartel',
            formato         VARCHAR(40)  NOT NULL DEFAULT 'personalizado',
            modo            VARCHAR(20)           DEFAULT NULL,
            ancho_mm        DECIMAL(8,2) NOT NULL DEFAULT 210,
            alto_mm         DECIMAL(8,2) NOT NULL DEFAULT 297,
            orientacion     VARCHAR(12)  NOT NULL DEFAULT 'vertical',
            dpi             INT          NOT NULL DEFAULT 300,
            contenido_json  LONGTEXT              DEFAULT NULL,
            thumbnail_path  VARCHAR(500)          DEFAULT NULL,
            creado          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            modificado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_pcarteles (id_empresa, id_proyecto)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS proyecto_carteles")
