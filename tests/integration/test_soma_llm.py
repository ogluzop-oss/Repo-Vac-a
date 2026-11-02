"""Integración · SOMA LLM (motor_llm.py / historial_llm.py) — tool-use real con Anthropic,
confirmación humana de escritura, aislamiento multiempresa, degradación honesta e historial de
conversación.

Regresión PERMANENTE del motor LLM de SOMA (migración desde un motor 100% basado en reglas a un
pipeline conversacional real, ver `src/services/copilot/motor_llm.py`), construida con el MISMO
rigor que `test_mcp_tools.py` (datos reales vía `fab`/`db`, aislamiento multiempresa explícito,
cero datos residuales).

Llamadas reales vs. simuladas: este entorno de desarrollo tiene un `ANTHROPIC_API_KEY` real en
`.env` (cargado automáticamente por `src.db.conexion` vía `load_dotenv()`), así que los escenarios
centrales (tool-use informativo, confirmación de escritura, aislamiento multiempresa, historial
multi-turno) usan la API REAL de Anthropic (modelo Haiku, barato) — mismo criterio "verificar
contra el sistema real, no un mock" que el resto de esta sesión. Los 3 casos de DEGRADACIÓN
(límite de coste / error inesperado / sin API key) se provocan deliberadamente con `monkeypatch`/
config, porque por definición no se pueden pedir a la API real bajo demanda de forma determinista
— cada uno documenta explícitamente por qué.
"""

from __future__ import annotations

import contextlib
import json

import pytest

pytestmark = pytest.mark.db

from src.services.copilot import historial_llm, motor_llm


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════════════════════
@contextlib.contextmanager
def _sesion_como(usuario: dict, id_empresa: str):
    """Simula una sesión de escritorio activa (usuario+empresa) en el hilo actual — mismo patrón
    que `tests/integration/test_rbac.py`. Necesario porque `motor_llm.responder_con_llm` resuelve
    tenant/usuario vía `ia_control_uso.resolver_tenant_actual()` → `sesion_global`/
    `empresa_actual_id()` (nunca de un argumento anónimo), igual que el resto del sistema."""
    from src.db.empresa import empresa_actual_id, set_empresa_actual
    from src.db.usuario import sesion_global

    previo_usuario = sesion_global.usuario_actual
    try:
        previo_empresa = empresa_actual_id()
    except Exception:
        previo_empresa = None
    sesion_global.usuario_actual = dict(usuario)
    set_empresa_actual(id_empresa)
    try:
        yield
    finally:
        sesion_global.usuario_actual = previo_usuario
        set_empresa_actual(previo_empresa)


def _borrar_reab_propuestas(db, codigo, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM reab_propuestas WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
        conn.commit()


def _contar_reab_propuestas(db, codigo, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM reab_propuestas WHERE codigo=%s AND id_empresa=%s",
                    (codigo, id_empresa))
        return cur.fetchone()[0]


def _borrar_historial(db, usuario, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM soma_conversaciones_turnos WHERE usuario=%s AND id_empresa=%s",
                    (str(usuario)[:80], id_empresa))
        conn.commit()


def _fila_turno(db, id_turno):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT tool_result_json, rol, tool_name FROM soma_conversaciones_turnos "
                    "WHERE id=%s", (id_turno,))
        return cur.fetchone()


@pytest.fixture
def empresa_llm(fab):
    return fab.empresa("EMP SOMA LLM")


@pytest.fixture
def usuario_llm(fab, empresa_llm):
    return fab.usuario(perfil="ADMINISTRADOR", id_empresa=empresa_llm)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Tool-use happy path: una pregunta real refleja el dato REAL sembrado
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestToolUseHappyPath:
    def test_pregunta_sobre_stock_refleja_la_cifra_real_sembrada(self, db, fab, empresa_llm, usuario_llm):
        # NOTA (mismo hallazgo ya documentado en test_mcp_tools.py): consultar_stock con 'codigo'
        # exacto devuelve el desglose de `stock_almacen` (0 sin filas ahí) — el dato real
        # sembrado por `fab.articulo` (Stock_total/Stock_tienda) vive en `articulos` y solo lo
        # devuelve la búsqueda por texto ('q'). Se pide por NOMBRE (no por código) para que Claude
        # use naturalmente ese camino y la respuesta pueda reflejar la cifra real sembrada.
        nombre_articulo = "Articulo SOMA Pregunta Stock Unico"
        fab.articulo(id_empresa=empresa_llm, nombre=nombre_articulo, stock_total=73, stock_tienda=12)
        fab.al_limpiar(lambda: _borrar_historial(db, usuario_llm["nombre"], empresa_llm))

        with _sesion_como(usuario_llm, empresa_llm):
            resp = motor_llm.responder_con_llm(
                f"Busca por NOMBRE (no tengo el código) el artículo '{nombre_articulo}' y dime "
                "cuántas unidades en TOTAL hay en stock. Responde solo con la cifra.",
                usuario_llm["nombre"], empresa_llm,
            )

        assert resp["via"] == "llm"
        assert "73" in resp["texto"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Confirmación humana de escritura — LA PROPIEDAD MÁS IMPORTANTE de esta pieza
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestConfirmacionEscritura:
    def test_confirmacion_afirmativa_ejecuta_la_tool_de_verdad(self, db, fab, empresa_llm, usuario_llm):
        codigo = fab.articulo(id_empresa=empresa_llm, nombre="Articulo SOMA Compra Confirmada")
        fab.al_limpiar(lambda: _borrar_reab_propuestas(db, codigo, empresa_llm))
        fab.al_limpiar(lambda: _borrar_historial(db, usuario_llm["nombre"], empresa_llm))

        assert _contar_reab_propuestas(db, codigo, empresa_llm) == 0

        with _sesion_como(usuario_llm, empresa_llm):
            r1 = motor_llm.responder_con_llm(
                f"Crea un borrador de pedido de compra para el artículo con código {codigo}, "
                "cantidad 5 unidades.",
                usuario_llm["nombre"], empresa_llm,
            )
        assert r1["via"] == "llm"
        assert r1.get("pendiente_confirmacion") is True
        # Nada se ha ejecutado todavía — CERO propuestas reales en BD.
        assert _contar_reab_propuestas(db, codigo, empresa_llm) == 0

        pendiente = historial_llm.obtener_turno_pendiente(usuario_llm["nombre"], empresa_llm)
        assert pendiente is not None
        assert pendiente["tool_name"] == "crear_borrador_pedido_compra"
        fila = _fila_turno(db, pendiente["id"])
        assert fila[0] is None   # tool_result_json IS NULL: propuesta aún PENDIENTE

        # Confirmación afirmativa EXPLÍCITA — sin coma pegada a la primera palabra (el
        # clasificador `_es_afirmativo` solo mira la primera palabra tras recortar puntuación de
        # los EXTREMOS, no de medio del texto).
        with _sesion_como(usuario_llm, empresa_llm):
            r2 = motor_llm.responder_con_llm("Sí", usuario_llm["nombre"], empresa_llm)
        assert r2["via"] == "llm"

        assert _contar_reab_propuestas(db, codigo, empresa_llm) == 1
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado FROM reab_propuestas WHERE codigo=%s AND id_empresa=%s",
                        (codigo, empresa_llm))
            estado = cur.fetchone()[0]
        assert estado == "pendiente"   # propuesta real, pendiente de aprobación humana (nunca auto-ejecutada)

        fila2 = _fila_turno(db, pendiente["id"])
        assert fila2[0] is not None   # tool_result_json YA poblado tras confirmar
        assert historial_llm.obtener_turno_pendiente(usuario_llm["nombre"], empresa_llm) is None

    def test_confirmacion_negativa_no_crea_ninguna_propuesta(self, db, fab, empresa_llm, usuario_llm):
        codigo = fab.articulo(id_empresa=empresa_llm, nombre="Articulo SOMA Compra Rechazada")
        fab.al_limpiar(lambda: _borrar_reab_propuestas(db, codigo, empresa_llm))
        fab.al_limpiar(lambda: _borrar_historial(db, usuario_llm["nombre"], empresa_llm))

        with _sesion_como(usuario_llm, empresa_llm):
            r1 = motor_llm.responder_con_llm(
                f"Crea un borrador de pedido de compra para el artículo con código {codigo}, "
                "cantidad 3 unidades.",
                usuario_llm["nombre"], empresa_llm,
            )
        assert r1.get("pendiente_confirmacion") is True
        pendiente = historial_llm.obtener_turno_pendiente(usuario_llm["nombre"], empresa_llm)
        assert pendiente is not None

        with _sesion_como(usuario_llm, empresa_llm):
            r2 = motor_llm.responder_con_llm("No, cancela esa propuesta por favor.",
                                             usuario_llm["nombre"], empresa_llm)
        assert r2["via"] == "llm"

        # NUNCA se creó una propuesta real para ese artículo.
        assert _contar_reab_propuestas(db, codigo, empresa_llm) == 0
        assert historial_llm.obtener_turno_pendiente(usuario_llm["nombre"], empresa_llm) is None
        fila = _fila_turno(db, pendiente["id"])
        assert json.loads(fila[0]) == {"cancelado": True}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Aislamiento multiempresa (misma rigurosidad que test_mcp_tools.py)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAislamientoMultiempresa:
    def test_sesion_de_empresa_a_nunca_toca_datos_de_empresa_b(self, db, fab):
        emp_a = fab.empresa("EMP SOMA LLM AISLADA A")
        emp_b = fab.empresa("EMP SOMA LLM AISLADA B")
        cod_a = fab.articulo(id_empresa=emp_a, nombre="SOMA LLM Aislado Solo A", stock_total=37,
                             stock_tienda=10)
        cod_b = fab.articulo(id_empresa=emp_b, nombre="SOMA LLM Aislado Solo B", stock_total=999,
                             stock_tienda=50)
        u = fab.usuario(perfil="ADMINISTRADOR", id_empresa=emp_a)
        fab.al_limpiar(lambda: _borrar_historial(db, u["nombre"], emp_a))

        # Espía sobre el punto REAL de ejecución de tools (no un mock de la llamada a Claude): deja
        # pasar la ejecución real, solo registra ctx/resultado para verificar el invariante.
        llamadas = []
        original = motor_llm._ejecutar_tool_segura

        def _spy(ctx, nombre_tool, argumentos):
            resultado = original(ctx, nombre_tool, argumentos)
            llamadas.append((dict(ctx), nombre_tool, dict(argumentos), resultado))
            return resultado

        import unittest.mock as _m
        with _m.patch.object(motor_llm, "_ejecutar_tool_segura", _spy):
            with _sesion_como(u, emp_a):
                resp = motor_llm.responder_con_llm(
                    f"¿Cuál es el stock total del artículo con código {cod_b}? Usa la "
                    "herramienta de stock para comprobarlo.",
                    u["nombre"], emp_a,
                )

        assert resp["via"] == "llm"
        assert llamadas, "se esperaba que Claude llamara a alguna tool de stock"
        # Invariante 1: TODA llamada a tool desde esta sesión se acotó a la empresa A, nunca B.
        for ctx, _nombre, _args, _resultado in llamadas:
            assert ctx["id_empresa"] == emp_a

        # Invariante 2: el resultado REAL de la tool para el código de B, visto desde la sesión de
        # A, viene aislado (0 — el mismo comportamiento que ya garantiza
        # test_mcp_tools.py::TestAislamientoMultiempresa para 'consultar_stock').
        consultas_b = [r for (_c, n, a, r) in llamadas
                      if n == "consultar_stock" and a.get("codigo") == cod_b]
        assert consultas_b, "Claude debía consultar el código indicado con 'codigo' exacto"
        assert consultas_b[0]["stock_total"] == 0
        assert consultas_b[0]["por_almacen"] == []
        # Invariante 3: la cifra REAL de B (999) nunca se cuela en la respuesta final al usuario de A.
        assert "999" not in resp["texto"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Degradación honesta — cada camino de fallo da (o deliberadamente NO da) un mensaje visible
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDegradacionHonesta:
    def test_limite_de_coste_ia_da_mensaje_amable(self, db, empresa_llm, usuario_llm):
        # Simulación DELIBERADA: no se puede pedir a la API real que "agote el límite de coste"
        # bajo demanda de forma determinista — se baja el límite diario de la empresa a 0.00 USD
        # (plan LIMITED), que `ia_control_uso.verificar_acceso_ia` bloquea ANTES de intentar
        # ninguna llamada real (cero coste/red en este test).
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE empresas SET ai_daily_cost_limit_usd=0.00 WHERE id_empresa=%s",
                        (empresa_llm,))
            conn.commit()
        try:
            with _sesion_como(usuario_llm, empresa_llm):
                resp = motor_llm.responder_con_llm("¿Cuánto stock hay?", usuario_llm["nombre"],
                                                   empresa_llm)
            assert resp["via"] == "fallback_needed"
            assert resp["motivo"] == "limite_ia"
            assert isinstance(resp.get("texto"), str) and resp["texto"].strip()
        finally:
            with db.obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM soma_conversaciones_turnos WHERE usuario=%s AND id_empresa=%s",
                            (usuario_llm["nombre"][:80], empresa_llm))
                cur.execute("UPDATE empresas SET ai_daily_cost_limit_usd=10.00, "
                            "ai_status='ACTIVE' WHERE id_empresa=%s", (empresa_llm,))
                conn.commit()

    def test_error_inesperado_generico_AHORA_tambien_da_mensaje_amable(
            self, db, fab, empresa_llm, usuario_llm, monkeypatch):
        # Simulación DELIBERADA (Parte 1 de este encargo, el gap corregido): un error que NO es ni
        # `LimiteUsoIAExcedido` ni uno de los 3 tipos `anthropic.*` reconocidos no se puede
        # provocar contra la API real de forma determinista — se fuerza con monkeypatch en un
        # punto interno del camino real (lectura de historial, dentro de `_turno_normal`) para
        # ejercitar la rama `except Exception` genérica EXACTAMENTE como la recorre el código real.
        fab.al_limpiar(lambda: _borrar_historial(db, usuario_llm["nombre"], empresa_llm))

        def _boom(*_a, **_k):
            raise RuntimeError("fallo interno simulado, no relacionado con Anthropic")

        monkeypatch.setattr(motor_llm.historial_llm, "obtener_historial", _boom)

        with _sesion_como(usuario_llm, empresa_llm):
            resp = motor_llm.responder_con_llm("¿Cuánto stock hay?", usuario_llm["nombre"],
                                               empresa_llm)

        assert resp["via"] == "fallback_needed"
        assert resp["motivo"] == "error_inesperado"
        # EL PUNTO CENTRAL de la Parte 1 de este encargo: antes de este fix, este camino devolvía
        # el dict SIN "texto" (fallback totalmente silencioso); ahora SIEMPRE lleva un aviso.
        assert isinstance(resp.get("texto"), str) and resp["texto"].strip()

    def test_sin_api_key_sigue_siendo_silencioso_A_PROPOSITO(self, empresa_llm, usuario_llm, monkeypatch):
        # Este caso NO debe llevar mensaje — es una condición de DESPLIEGUE (no hay
        # ANTHROPIC_API_KEY en el proceso), no un fallo en tiempo de ejecución; degradar en
        # silencio aquí es intencional y documentado en `motor_llm.py` — confirmamos que sigue
        # siendo así tras el cambio de la Parte 1 (que solo tocó la rama de error genérico).
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with _sesion_como(usuario_llm, empresa_llm):
            resp = motor_llm.responder_con_llm("¿Cuánto stock hay?", usuario_llm["nombre"],
                                               empresa_llm)

        assert resp == {"via": "fallback_needed", "motivo": "sin_api_key"}
        assert "texto" not in resp


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Historial de conversación: la segunda pregunta depende del contexto de la primera
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestHistorialConversacion:
    def test_segunda_pregunta_usa_el_contexto_de_la_primera(self, db, fab, empresa_llm, usuario_llm):
        # Por NOMBRE (no por código): ver nota en TestToolUseHappyPath — solo la búsqueda por texto
        # ('q') devuelve el Stock_total/Stock_tienda real sembrado en `articulos`.
        nombre_articulo = "Articulo SOMA Historial Contexto Unico"
        fab.articulo(id_empresa=empresa_llm, nombre=nombre_articulo, stock_total=55, stock_tienda=21)
        fab.al_limpiar(lambda: _borrar_historial(db, usuario_llm["nombre"], empresa_llm))

        with _sesion_como(usuario_llm, empresa_llm):
            r1 = motor_llm.responder_con_llm(
                f"Busca por NOMBRE el artículo '{nombre_articulo}' y dime su stock TOTAL.",
                usuario_llm["nombre"], empresa_llm,
            )
            # Pregunta de seguimiento que NO repite el nombre — depende del contexto del turno 1.
            r2 = motor_llm.responder_con_llm(
                "¿Y cuántas unidades hay en la TIENDA de ese mismo artículo?",
                usuario_llm["nombre"], empresa_llm,
            )

        assert "55" in r1["texto"]
        assert "21" in r2["texto"]

        historial = historial_llm.obtener_historial(usuario_llm["nombre"], empresa_llm, limite=20)
        roles = [h["role"] for h in historial]
        # Round-trip correcto en BD: 2 turnos de usuario + 2 de asistente, en orden cronológico.
        assert roles == ["user", "assistant", "user", "assistant"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. kernel.py — smoke test de integración del aviso de degradación (`aviso_degradacion`)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestKernelIntegracionAvisoDegradacion:
    def test_worker_antepone_el_aviso_de_degradacion_a_la_respuesta_determinista(
            self, monkeypatch, empresa_llm, usuario_llm):
        """Ejercita el camino REAL de `SomaKernel._consultar_cerebro` (hilo de fondo real, señal Qt
        real) — no una reimplementación de su lógica. Se monkeypatchea solo lo que haría falta
        monkeypatchear en producción para forzar una degradación determinista (`motor_llm` y el
        `cerebro()` determinista), igual de aislado que un test de `kernel.py` necesita estar del
        contenido real de ambos motores."""
        import time as _time

        from PyQt6.QtWidgets import QApplication

        from src.services.copilot import motor_llm as _mllm
        from src.soma import razonador as _razonador
        from src.soma.kernel import SomaKernel

        aviso = "AVISO DE DEGRADACION DE PRUEBA"
        determinista = "RESPUESTA DETERMINISTA DE PRUEBA"

        monkeypatch.setattr(
            _mllm, "responder_con_llm",
            lambda texto, usuario, empresa: {
                "via": "fallback_needed", "motivo": "limite_ia", "texto": aviso,
            },
        )
        monkeypatch.setattr(_razonador, "es_analitica", lambda texto: False)

        class _CerebroFalso:
            def preguntar(self, texto, usuario, id_empresa):
                return {"texto": determinista}

        kernel = SomaKernel()
        monkeypatch.setattr(kernel, "cerebro", lambda: _CerebroFalso())

        capturado = {}

        def _capturar(resp, t0, texto):
            capturado["resp"] = resp

        kernel._puente.lista.connect(_capturar)

        with _sesion_como(usuario_llm, empresa_llm):
            kernel._consultar_cerebro("¿cuánto stock hay?")

            app = QApplication.instance()
            t0 = _time.time()
            while "resp" not in capturado and _time.time() - t0 < 10:
                if app is not None:
                    app.processEvents()
                _time.sleep(0.05)

        assert "resp" in capturado, "el worker de _consultar_cerebro no emitió respuesta a tiempo"
        resp = capturado["resp"]
        assert resp["texto"] == f"{aviso}\n\n{determinista}"
