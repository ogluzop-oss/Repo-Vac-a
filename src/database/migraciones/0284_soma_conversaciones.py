"""
Migracion 0284 — Historial de conversacion LLM de SOMA. ADITIVA, idempotente, reversible.

Contexto: SOMA migra de un motor 100% basado en reglas a un pipeline conversacional real con la
API de Anthropic (tool-use). A diferencia de `soma_memoria` (0097 — habitos/preferencias
aprendidas LENTAMENTE, nunca texto de conversacion) y de `copilot.memoria` (resumen de
dominio/periodo consultado, sin texto), ninguna tabla existente guarda el HISTORIAL REAL de
turnos usuario/asistente que `messages.create` necesita para mantener contexto entre mensajes —
de ahi esta tabla nueva, propia de esa responsabilidad (ver `services/copilot/historial_llm.py`).

Tambien es el soporte de la maquina de estados de confirmacion humana ante una tool de ESCRITURA
(`crear_borrador_pedido_compra`/`gestionar_articulo_catalogo`, `requiere_confirmacion=True` en
`mcp_server/registry.py`): una fila rol='tool' con `tool_result_json IS NULL` marca una propuesta
de tool PENDIENTE de confirmacion humana en el turno siguiente (ver `services/copilot/motor_llm.py`).
"""

VERSION = "0284"
DESCRIPCION = "Historial de conversacion LLM de SOMA: soma_conversaciones_turnos"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("soma_conversaciones_turnos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        usuario VARCHAR(80) NOT NULL,
        rol VARCHAR(10) NOT NULL,
        contenido MEDIUMTEXT DEFAULT NULL,
        tool_name VARCHAR(120) DEFAULT NULL,
        tool_args_json MEDIUMTEXT DEFAULT NULL,
        tool_result_json MEDIUMTEXT DEFAULT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_soma_conv (id_empresa, usuario, creado_en)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
