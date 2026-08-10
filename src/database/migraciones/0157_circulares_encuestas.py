"""
Migración 0157 — Circulares y Encuestas internas (comunicación entre centros). ADITIVA, reversible.

Bandeja interna de la empresa para comunicación entre centros:
  · CIRCULARES: mensaje del emisor con título/subtítulo(auto)/cuerpo + adjuntos (texto/imagen inline);
    cada centro confirma la lectura (perfil + contraseña) y puede añadir comentario y adjuntos.
  · ENCUESTAS: texto introductorio + preguntas (de opciones o de texto libre) con opciones ilimitadas;
    cada centro responde (marcando casillas / "Otro" con texto / texto libre) + comentario + adjuntos.

Multiempresa estricto (clave por id_empresa). Adjuntos UNIFICADOS en una tabla para ambos tipos y para
los envíos en primera instancia (EMISOR) y las respuestas (RESPUESTA). No crea motor nuevo: es la
persistencia de la bandeja interna dentro del módulo de Correo.
"""

VERSION = "0157"
DESCRIPCION = "Comunicación interna: circulares + encuestas + confirmaciones/respuestas + adjuntos"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("com_circulares", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(64) NOT NULL,
        titulo VARCHAR(255) NOT NULL,
        cuerpo MEDIUMTEXT,
        creador_id VARCHAR(64) DEFAULT NULL,
        creador_nombre VARCHAR(120) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        estado VARCHAR(20) NOT NULL DEFAULT 'PUBLICADA',
        INDEX idx_circ_emp (id_empresa, creado)
    """),
    ("com_circular_confirmaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_circular BIGINT NOT NULL,
        usuario_id VARCHAR(64) DEFAULT NULL,
        usuario_nombre VARCHAR(120) DEFAULT NULL,
        id_centro VARCHAR(64) DEFAULT NULL,
        comentario MEDIUMTEXT,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_cconf_circ (id_circular, creado)
    """),
    ("com_encuestas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(64) NOT NULL,
        titulo VARCHAR(255) NOT NULL,
        intro MEDIUMTEXT,
        creador_id VARCHAR(64) DEFAULT NULL,
        creador_nombre VARCHAR(120) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        estado VARCHAR(20) NOT NULL DEFAULT 'PUBLICADA',
        INDEX idx_enc_emp (id_empresa, creado)
    """),
    ("com_encuesta_preguntas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_encuesta BIGINT NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        texto MEDIUMTEXT,
        tipo VARCHAR(20) NOT NULL DEFAULT 'OPCIONES',
        INDEX idx_epreg_enc (id_encuesta, orden)
    """),
    ("com_encuesta_opciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_pregunta BIGINT NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        texto VARCHAR(500),
        INDEX idx_eopc_preg (id_pregunta, orden)
    """),
    ("com_encuesta_respuestas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_encuesta BIGINT NOT NULL,
        usuario_id VARCHAR(64) DEFAULT NULL,
        usuario_nombre VARCHAR(120) DEFAULT NULL,
        id_centro VARCHAR(64) DEFAULT NULL,
        comentario MEDIUMTEXT,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_eresp_enc (id_encuesta, creado)
    """),
    ("com_encuesta_resp_items", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_respuesta BIGINT NOT NULL,
        id_pregunta BIGINT NOT NULL,
        id_opcion BIGINT DEFAULT NULL,
        texto MEDIUMTEXT,
        INDEX idx_eri_resp (id_respuesta),
        INDEX idx_eri_preg (id_pregunta)
    """),
    ("com_adjuntos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        tipo_entidad VARCHAR(20) NOT NULL,
        id_entidad BIGINT NOT NULL,
        origen VARCHAR(20) NOT NULL DEFAULT 'EMISOR',
        id_respuesta BIGINT DEFAULT NULL,
        clase VARCHAR(20) NOT NULL DEFAULT 'texto',
        nombre VARCHAR(255),
        ruta VARCHAR(500),
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_adj_ent (tipo_entidad, id_entidad, origen),
        INDEX idx_adj_resp (id_respuesta)
    """),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                    f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
