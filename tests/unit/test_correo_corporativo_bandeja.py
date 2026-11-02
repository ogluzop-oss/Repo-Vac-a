"""
Bandeja unificada de CORREO (Gmail + circulares + encuestas) — `gui.correo_corporativo.
CorreoCorporativoWindow`. Smoke offscreen + datos reales en BD.

Cubre la restructuración de esta sesión: fusión de las tres fuentes en «Recibidos», clic-para-
expandir estilo Gmail (oculta la lista, muestra el contenido), negrita en vez de columna "LEÍDO",
columna lateral de 7 carpetas — TODAS con datos reales desde la migración 0288 (Borradores/
Papelera/Programados/Pospuestos/Importantes dejaron de mostrar el aviso honesto de "no disponible":
ver `tests/integration/test_correo_carpetas.py` para el ciclo completo de cada una a nivel de
servicio; aquí solo se cubre que la GUI las pinta como carpeta REAL —lista vacía real cuando no hay
datos, nunca el aviso de "no disponible"— y la eliminación del popup «VER COMUNICADOS» /
`BandejaComunicacionDialog` (Strangler Pattern: la clase sigue existiendo en `circulares_gui.py`,
solo deja de estar enlazada desde esta ventana).
"""

import inspect

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QLabel

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def entorno_bandeja(fab):
    """Empresa de prueba con: un buzón Gmail "conectado" (token presente) + un mensaje recibido
    real, y una circular + una encuesta dirigidas (destinatario PARA) al usuario de prueba."""
    from src.db import correo as correo_db
    from src.db.empresa import EMPRESA_DEFAULT_ID, empresa_actual_id, set_empresa_actual
    from src.db.usuario import sesion_global
    from src.services.comunicacion_interna import circulares, encuestas

    emp = fab.empresa("EMPRESA CORREO TEST")
    user = fab.usuario(nombre="USR_BANDEJA_CORREO", id_empresa=emp, email="bandeja@test.com")

    cid = fab.buzon_correo(id_empresa=emp)
    correo_db.actualizar_correo(cid, proveedor="google")
    correo_db.guardar_tokens(cid, "google", access_token="tok-test-bandeja")
    fab.al_limpiar(lambda: correo_db.revocar_tokens(cid))
    correo_db.guardar_recibido(cid, "remitente@ejemplo.com", "Asunto de prueba Gmail",
                              "Cuerpo del mensaje de prueba.", message_id="MID-BANDEJA-TEST-1",
                              id_empresa=emp)

    def _limpiar_recibidos():
        with fab.cx.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM correos_recibidos WHERE id_correo=%s", (cid,))
            conn.commit()
    fab.al_limpiar(_limpiar_recibidos)

    u = {"id": user["id"], "nombre": user["nombre"]}
    rc = circulares.crear_circular(
        "Circular de prueba bandeja", "Cuerpo circular",
        destinatarios=[{"usuario_id": user["id"], "tipo": "PARA"}], usuario=u, id_empresa=emp)
    assert rc["ok"], rc
    re_ = encuestas.crear_encuesta(
        "Encuesta de prueba bandeja", "intro", [{"texto": "P1", "tipo": "TEXTO"}],
        destinatarios=[{"usuario_id": user["id"], "tipo": "PARA"}], usuario=u, id_empresa=emp)
    assert re_["ok"], re_

    empresa_previa = empresa_actual_id()
    usuario_previo = sesion_global.usuario_actual
    set_empresa_actual(emp)
    # Perfil SUPERADMIN: ve todos los botones de creación (NUEVO MENSAJE + NUEVA ENCUESTA), para
    # que el test de alineación de botones cubra la fila completa.
    sesion_global.usuario_actual = {"id": user["id"], "nombre": user["nombre"],
                                    "perfil": "SUPERADMIN", "id_empresa": emp}
    try:
        yield {"emp": emp, "user": user, "id_circular": rc["id"], "id_encuesta": re_["id"],
              "id_correo": cid}
    finally:
        sesion_global.usuario_actual = usuario_previo
        set_empresa_actual(empresa_previa or EMPRESA_DEFAULT_ID)
        circulares.eliminar_circular(rc["id"])
        encuestas.eliminar_encuesta(re_["id"])


def _negrita_col0(tabla, row):
    """La columna 0 (REMITENTE) ya no es un `QTableWidgetItem` — ahora es un widget
    (`_FilaRemitenteCelda`: casilla de selección múltiple + texto, compartiendo celda, petición
    explícita del usuario). Lee la negrita desde el `QLabel` interno de ese widget."""
    celda = tabla.cellWidget(row, 0)
    lbl = celda.findChild(QLabel)
    return lbl.font().bold()


def test_bandeja_unificada_incluye_las_tres_fuentes(app, entorno_bandeja):
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        tipos = {f["tipo"] for f in win._filas}
        assert tipos == {"gmail", "circular", "encuesta"}, win._filas
        ids_circular = {f["id"] for f in win._filas if f["tipo"] == "circular"}
        ids_encuesta = {f["id"] for f in win._filas if f["tipo"] == "encuesta"}
        assert entorno_bandeja["id_circular"] in ids_circular
        assert entorno_bandeja["id_encuesta"] in ids_encuesta
        # Columnas de la lista: sin "LEÍDO" (negrita en vez de columna, como Gmail).
        assert win.tabla.columnCount() == 3
    finally:
        win.deleteLater()


def test_click_fila_gmail_oculta_lista_y_muestra_contenido(app, entorno_bandeja):
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        assert win._stack.currentWidget() is win._pagina_lista
        row_gmail = next(i for i, f in enumerate(win._filas) if f["tipo"] == "gmail")
        win._abrir_fila_unificada(row_gmail, 0)
        assert win._stack.currentWidget() is win._pagina_detalle
        assert win._stack.currentIndex() == 1
        win._volver_a_lista()
        assert win._stack.currentWidget() is win._pagina_lista
    finally:
        win.deleteLater()


def test_ver_comunicados_eliminado_del_archivo():
    """El popup «VER COMUNICADOS» (`BandejaComunicacionDialog`) ya no se INVOCA desde esta
    ventana — Strangler Pattern: la clase sigue existiendo en `circulares_gui.py` (huérfana), y
    esta ventana puede seguir *mencionándola* en comentarios/docstrings explicando la migración,
    pero nunca debe importarla ni instanciarla."""
    from src.gui import correo_corporativo
    codigo = inspect.getsource(correo_corporativo)
    assert "import BandejaComunicacionDialog" not in codigo
    assert "BandejaComunicacionDialog(" not in codigo
    assert "VER COMUNICADOS" not in codigo
    assert "_ver_comunicados" not in codigo
    assert "correo.ver_comunicados" not in codigo


def test_sidebar_7_carpetas(app, entorno_bandeja):
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        esperadas = {"recibidos", "pospuestos", "enviados", "borradores", "papelera",
                    "programados", "importantes"}
        assert set(win._botones_carpeta.keys()) == esperadas
        assert win._botones_carpeta["recibidos"].isChecked()
    finally:
        win.deleteLater()


@pytest.mark.parametrize("carpeta", ["importantes", "pospuestos", "borradores", "papelera",
                                     "programados"])
def test_carpetas_reales_sin_datos_muestran_vacio_real(app, entorno_bandeja, carpeta):
    """Desde la migración 0288 las 5 carpetas tienen backend real (ver
    `tests/integration/test_correo_carpetas.py`) — sin datos para el usuario de prueba, deben
    mostrar la lista VACÍA REAL (`lbl_carpeta_vacia`), nunca el aviso de "no disponible" que
    mostraban antes de esta sesión."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win._cambiar_carpeta(carpeta)
        assert win._pagina_lista.findChild(QLabel, "lbl_no_disponible") is None, \
            f"carpeta {carpeta} todavía muestra el aviso de no-disponible (debería ser real)"
        assert win._pagina_lista.findChild(QLabel, "lbl_carpeta_vacia") is not None, \
            f"carpeta {carpeta} no muestra la lista vacía real"
    finally:
        win.deleteLater()


def test_carpeta_borradores_muestra_borrador_real(app, entorno_bandeja):
    """No se simula el doble-clic de reapertura aquí: `_abrir_fila_unificada` abre el compositor
    con `.exec()` (modal, bucle de eventos propio) — llamarlo en un test automatizado colgaría el
    proceso. El ciclo completo guardar/reabrir/editar/publicar YA está cubierto a nivel de servicio
    en `tests/integration/test_correo_carpetas.py`; aquí solo se verifica que la carpeta Borradores
    de la GUI pinta de verdad el borrador (no el aviso de "no disponible" ni una lista vacía)."""
    from src.services.comunicacion_interna import circulares
    from src.gui.correo_corporativo import CorreoCorporativoWindow

    u = entorno_bandeja["user"]
    r = circulares.guardar_borrador(titulo="Borrador bandeja test", cuerpo="cuerpo",
                                    usuario={"id": u["id"], "nombre": u["nombre"]},
                                    id_empresa=entorno_bandeja["emp"])
    assert r["ok"] is True
    cid = r["id"]
    win = CorreoCorporativoWindow()
    try:
        win._cambiar_carpeta("borradores")
        ids = {f["id"] for f in win._filas if f["tipo"] == "circular"}
        assert cid in ids
        assert win._pagina_lista.findChild(QLabel, "lbl_carpeta_vacia") is None
    finally:
        win.deleteLater()
        circulares.eliminar_circular(cid)


def test_carpeta_enviados_muestra_lo_creado_por_el_usuario(app, entorno_bandeja):
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win._cambiar_carpeta("enviados")
        ids = {f["id"] for f in win._filas if f["tipo"] == "circular"}
        assert entorno_bandeja["id_circular"] in ids
        # No aviso de "no disponible" (Enviados SÍ tiene datos reales).
        assert win._pagina_lista.findChild(QLabel, "lbl_no_disponible") is None
    finally:
        win.deleteLater()


def test_botones_accion_misma_altura(app, entorno_bandeja):
    """Los botones de la barra superior (NUEVO MENSAJE/NUEVA ENCUESTA/AGENDA/CCP/CONFIGURAR
    CORREO/SINCRONIZAR) deben quedar a la misma altura (misma fila), sin ninguno flotando aparte."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win.resize(1200, 800)
        win.show()
        app.processEvents()
        assert len(win._botones_accion) >= 5
        ys = {b.y() for b in win._botones_accion}
        assert len(ys) == 1, f"botones de la barra de acciones no alineados (y distintos): {ys}"
    finally:
        win.hide()
        win.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar ENTERPRISE (estructura): root = QHBoxLayout con el sidebar como primer hijo, span de
# toda la altura, título/acciones fuera de su propio layout — ver CLAUDE.md (reglas de shell).
# ─────────────────────────────────────────────────────────────────────────────

_NOMBRES_SIDEBAR_GLOBALES = {"sidebar", "sidebar_admin", "sidebar_logistica", "sidebar_modulo"}
_TEXTOS_PROHIBIDOS_EN_SIDEBAR = {
    "NUEVO MENSAJE", "NUEVA ENCUESTA", "AGENDA", "CCP",
    "CONFIGURAR CORREO", "SINCRONIZAR", "CORREO CORPORATIVO",
}


def test_sidebar_es_hijo_directo_del_layout_raiz_horizontal(app, entorno_bandeja):
    """El layout raíz de la ventana debe ser un QHBoxLayout (no un QVBoxLayout con la cabecera
    arriba) y el sidebar debe ser su PRIMER hijo directo — así ocupa toda la altura, en vez de
    quedar encajado bajo la cabecera/barra de acciones como antes."""
    from PyQt6.QtWidgets import QHBoxLayout
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        raiz = win.layout()
        assert isinstance(raiz, QHBoxLayout), f"layout raíz debería ser QHBoxLayout, es {type(raiz)}"
        assert raiz.itemAt(0).widget() is win._sidebar, \
            "el sidebar debe ser el primer widget directo del layout raíz"
        assert raiz.itemAt(0).widget().parentWidget() is win
    finally:
        win.deleteLater()


def test_sidebar_objectname_reconocido_globalmente(app, entorno_bandeja):
    """El QFrame del sidebar debe usar uno de los 4 objectNames que `QSS_SIDEBAR`
    (`assets/estilo_global.py`) ya estiliza globalmente (background/borde), igual que
    `recepcion_pale.py` ("sidebar_logistica"). El título debe usar el objectName compañero."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        assert win._sidebar.objectName() in _NOMBRES_SIDEBAR_GLOBALES, win._sidebar.objectName()
        titulo = win._sidebar.findChild(QLabel, "sidebar_title")
        assert titulo is not None, "falta un QLabel con objectName='sidebar_title' en el sidebar"
        assert "SMART MAIL" in titulo.text()
    finally:
        win.deleteLater()


def test_sidebar_ocupa_toda_la_altura_de_la_ventana(app, entorno_bandeja):
    """El sidebar debe abarcar de arriba a abajo de la ventana (geometría), no solo la parte bajo
    la cabecera/barra de acciones."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win.resize(1200, 800)
        win.show()
        app.processEvents()
        assert win._sidebar.y() == 0
        assert win._sidebar.height() == win.height(), \
            f"sidebar.height()={win._sidebar.height()} != window.height()={win.height()}"
        assert win._sidebar.width() == 280
    finally:
        win.hide()
        win.deleteLater()


def test_titulo_y_acciones_fuera_del_layout_del_sidebar(app, entorno_bandeja):
    """La cabecera ("CORREO CORPORATIVO" + ✕) y la barra de acciones (NUEVO MENSAJE/NUEVA
    ENCUESTA/AGENDA/CCP/CONFIGURAR CORREO/SINCRONIZAR) NO deben vivir dentro del layout propio del
    sidebar — deben quedar en la columna de contenido, a la derecha."""
    from PyQt6.QtWidgets import QPushButton
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        for btn in win._sidebar.findChildren(QPushButton):
            texto = btn.text().upper()
            assert not any(p in texto for p in _TEXTOS_PROHIBIDOS_EN_SIDEBAR), \
                f"botón de la cabecera/acciones filtrado dentro del sidebar: {btn.text()!r}"
        for lbl in win._sidebar.findChildren(QLabel):
            assert "CORREO CORPORATIVO" not in lbl.text().upper()
        # Los 7 botones de carpeta SÍ deben estar, y deben ser hijos del sidebar.
        for cid, btn in win._botones_carpeta.items():
            assert btn.parentWidget() is win._sidebar, cid
    finally:
        win.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# Bold/no-leído: Recibidos debe limpiar la negrita al abrir; Enviados SIEMPRE negrita.
# ─────────────────────────────────────────────────────────────────────────────

def test_abrir_fila_gmail_en_recibidos_quita_la_negrita(app, entorno_bandeja):
    """Abrir (clic) un mensaje Gmail no leído en Recibidos debe limpiar su negrita de inmediato,
    en la misma tabla (clic-para-expandir estilo Gmail, sin re-render completo)."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        row_gmail = next(i for i, f in enumerate(win._filas) if f["tipo"] == "gmail")
        assert _negrita_col0(win.tabla, row_gmail) is True, \
            "el mensaje de prueba debería empezar sin leer (negrita)"
        win._abrir_fila_unificada(row_gmail, 0)
        assert _negrita_col0(win.tabla, row_gmail) is False, \
            "la negrita debería desaparecer tras abrir el mensaje"
        assert win._filas[row_gmail]["leido"] is True
    finally:
        win.deleteLater()


def test_abrir_fila_circular_en_recibidos_quita_la_negrita_en_siguiente_render(app, entorno_bandeja):
    """Para circulares/encuestas no se simula el clic completo (el visor es modal, `.exec()`
    colgaría el test — mismo motivo documentado en `test_carpeta_borradores_muestra_borrador_real`).
    Se invoca directamente el mismo camino que usa `_abrir_fila_unificada` tras cerrarse el visor:
    marcar leído + repintar + la red de seguridad `_forzar_leido_en_memoria`. Cubre exactamente lo
    que pide el bug: que el negrita desaparezca "en el siguiente render", sea cual sea el motivo
    (recarga de BD o la red de seguridad en memoria)."""
    from src.services.comunicacion_interna import circulares
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        row = next(i for i, f in enumerate(win._filas) if f["tipo"] == "circular")
        id_circular = win._filas[row]["id"]
        assert _negrita_col0(win.tabla, row) is True

        u = entorno_bandeja["user"]
        circulares.marcar_leido_circular(id_circular, u["id"])
        win._pintar_carpeta()
        win._forzar_leido_en_memoria("circular", id_circular)

        fila_tras = next(f for f in win._filas if f["tipo"] == "circular" and f["id"] == id_circular)
        assert fila_tras["leido"] is True
        fila_idx = win._filas.index(fila_tras)
        assert _negrita_col0(win.tabla, fila_idx) is False
    finally:
        win.deleteLater()


def test_carpeta_enviados_siempre_en_negrita(app, entorno_bandeja):
    """Enviados debe mostrar SIEMPRE sus filas en negrita, sin importar el flag `leido` subyacente
    (elección deliberada del usuario — no depende de si se ha abierto o no)."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win._cambiar_carpeta("enviados")
        assert win._filas, "se esperaba al menos una fila en Enviados"
        assert all(f.get("leido") for f in win._filas), \
            "fixture inesperado: Enviados ya no marca leido=True en sus filas"
        for r in range(win.tabla.rowCount()):
            assert _negrita_col0(win.tabla, r) is True, f"fila {r} col 0 de Enviados no está en negrita"
            for col in range(1, win.tabla.columnCount()):
                it = win.tabla.item(r, col)
                assert it.font().bold() is True, f"fila {r} col {col} de Enviados no está en negrita"
    finally:
        win.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# Importante/Posponer: mismo turquesa estándar que `_btn_accion(primary=True)` (Papelera sigue roja).
# ─────────────────────────────────────────────────────────────────────────────

def test_botones_importante_posponer_usan_el_turquesa_estandar(app, entorno_bandeja):
    from src.gui.correo_corporativo import CorreoCorporativoWindow, _btn_accion
    win = CorreoCorporativoWindow()
    try:
        assert win._carpeta_actual == "recibidos"
        fila = win._fila_acciones_carpeta()
        referencia = _btn_accion("X", lambda: None, primary=True)
        esperado = referencia.styleSheet()

        encontrados = {}
        for i in range(fila.count()):
            w = fila.itemAt(i).widget()
            if w is None:
                continue
            txt = w.text().upper()
            if "IMPORTANTE" in txt and "QUITAR" not in txt:
                encontrados["importante"] = w
            elif "POSPONER" in txt:
                encontrados["posponer"] = w
            elif "PAPELERA" in txt:
                encontrados["papelera"] = w

        assert "importante" in encontrados and "posponer" in encontrados, encontrados
        assert encontrados["importante"].styleSheet() == esperado
        assert encontrados["posponer"].styleSheet() == esperado
        # Papelera se queda roja/danger — NO debe coincidir con el turquesa estándar.
        assert encontrados["papelera"].styleSheet() != esperado
    finally:
        win.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# Dos bugs reales reportados tras el primer intento de animación de carpeta: (1) una animación en
# marcha no se detenía antes de arrancar la siguiente, pudiendo dejar el contenido "a medias"; (2)
# `destino = widget.pos()` podía leer una geometría todavía no asentada tras `_pintar_carpeta()`.
# ─────────────────────────────────────────────────────────────────────────────

def test_cambio_de_carpeta_detiene_la_animacion_anterior_antes_de_empezar_otra(app, entorno_bandeja):
    """Si se cambia de carpeta antes de que termine la animación anterior (240ms), la anterior debe
    detenerse — nunca dos `QPropertyAnimation` corriendo a la vez sobre el mismo widget/propiedad
    (causa real del "se queda atascada a mitad, cortando el contenido"). Desde que el cambio de
    carpeta reutiliza el motor COMPARTIDO `transiciones._deslizar` (mismo recorrido/duración que el
    resto de la app), la animación entrante vive en `_pagina_lista._a_in` (atributo que `_deslizar`
    deja ahí él mismo), no en un atributo propio de la ventana."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win.resize(1200, 800)
        win.show()
        app.processEvents()
        win._cambiar_carpeta("pospuestos")
        anim_1 = win._pagina_lista._a_in
        assert anim_1.state().name == "Running"
        # Cambiar de carpeta OTRA VEZ antes de que la primera termine (no se deja correr el reloj).
        win._cambiar_carpeta("enviados")
        anim_2 = win._pagina_lista._a_in
        assert anim_1 is not anim_2
        assert anim_1.state().name == "Stopped", "la animación anterior debía haberse detenido"
    finally:
        win.hide()
        win.deleteLater()


def test_cambio_de_carpeta_destino_siempre_es_origen_del_stack(app, entorno_bandeja):
    """`destino` ya no se lee de `widget.pos()` (podía estar sin asentar tras `_pintar_carpeta()`):
    un `QStackedWidget` posiciona SIEMPRE su página actual en (0,0) dentro de sí mismo, así que la
    animación debe terminar exactamente ahí, con independencia de cualquier timing de layout."""
    from PyQt6.QtCore import QPoint
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win.resize(1200, 800)
        win.show()
        app.processEvents()
        win._cambiar_carpeta("papelera")   # carpeta con fila de acciones (altura distinta a Recibidos)
        anim = win._pagina_lista._a_in
        assert anim.endValue() == QPoint(0, 0)
    finally:
        win.hide()
        win.deleteLater()


def test_botones_carpeta_sidebar_en_mayusculas_y_tamano_base(app, entorno_bandeja):
    """Petición explícita: los textos de las pestañas del sidebar (Recibidos/Pospuestos/etc.) deben
    ir en MAYÚSCULAS (igual que "SALIR"/el resto de sidebars de la app). El tamaño subió dos veces
    (12px -> 13px -> 14px) y luego el usuario pidió bajarlo 2 puntos de nuevo — vuelve a ser el
    tamaño BASE de `_SidebarBtn` (12px, sin override local)."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        assert win._botones_carpeta, "no se encontraron botones de carpeta"
        for cid, btn in win._botones_carpeta.items():
            assert btn.text() == btn.text().upper(), f"{cid}: {btn.text()!r} no está en mayúsculas"
            assert "font-size:12px" in btn.styleSheet().replace(" ", ""), cid
            assert "font-size:13px" not in btn.styleSheet().replace(" ", ""), cid
            assert "font-size:14px" not in btn.styleSheet().replace(" ", ""), cid
    finally:
        win.deleteLater()


def test_cambio_de_carpeta_direccion_es_siempre_la_misma_sin_importar_el_orden(app, entorno_bandeja):
    """Bug real reportado tras el fix anterior: el signo del desplazamiento se calculaba comparando
    el índice de la carpeta anterior/nueva EN EL SIDEBAR (adelante=derecha, atrás=izquierda). Como
    `recibidos` es siempre la carpeta inicial (índice 0), la primera navegación SIEMPRE era "hacia
    delante" (correcta), pero la segunda -en cuanto el par de carpetas no seguía el orden ascendente
    del sidebar- invertía el signo, percibido como aleatorio/bugeado. Ahora la dirección es
    constante: debe ser la MISMA tanto yendo "hacia delante" (recibidos→importantes) como "hacia
    atrás" (importantes→recibidos)."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win.resize(1200, 800)
        win.show()
        app.processEvents()

        win._cambiar_carpeta("importantes")   # hacia delante en el sidebar (recibidos -> importantes)
        offset_adelante = win._pagina_lista._a_in.startValue().x()

        win._cambiar_carpeta("recibidos")     # hacia atrás en el sidebar (importantes -> recibidos)
        offset_atras = win._pagina_lista._a_in.startValue().x()

        # El SIGNO debe coincidir (misma dirección siempre) — la MAGNITUD puede variar legítimamente
        # entre llamadas (el motor compartido `_deslizar` recalcula el recorrido contra el ancho real
        # del contenedor en cada transición, que puede fluctuar levemente con el layout asentándose).
        assert (offset_adelante < 0) == (offset_atras < 0), (
            "la dirección del deslizamiento no debe depender del orden de las carpetas en el sidebar")
    finally:
        win.hide()
        win.deleteLater()


def test_boton_salir_tiene_estilo_hover_rojo_explicito(app, entorno_bandeja):
    """El `:hover` del botón SALIR no se repintaba de forma fiable solo con el QSS global (esta
    ventana tiene su propio `setStyleSheet()` en la raíz, lo que rompe la cascada por objectName
    para pseudo-estados) — ahora lleva un estilo inline explícito con la regla `:hover` incluida."""
    from PyQt6.QtWidgets import QPushButton
    from src.gui.correo_corporativo import CorreoCorporativoWindow, _BG, _ROJO
    win = CorreoCorporativoWindow(callback_vuelta=lambda: None)
    try:
        botones_salir = [b for b in win._sidebar.findChildren(QPushButton)
                         if b.objectName() == "btn_sidebar_exit"]
        assert len(botones_salir) == 1
        hoja = botones_salir[0].styleSheet()
        assert ":hover" in hoja
        assert f"background-color:{_ROJO}" in hoja.replace(" ", "")
        assert f"color:{_BG}" in hoja.replace(" ", "")
    finally:
        win.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# Casillas de selección múltiple en la columna REMITENTE (petición explícita: "por si el usuario
# necesita realizar la misma acción en más de un mensaje a la vez"; comparten celda con el texto
# del remitente, SIN columna aparte).
# ─────────────────────────────────────────────────────────────────────────────

def test_columna_remitente_tiene_casilla_de_seleccion_sin_columna_aparte(app, entorno_bandeja):
    """La columna 0 sigue siendo una sola columna ("REMITENTE") — la casilla comparte celda con el
    texto, no se añade una columna nueva."""
    from PyQt6.QtWidgets import QCheckBox, QLabel
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        assert win.tabla.columnCount() == 3, "no debe haber una columna nueva para la casilla"
        assert win.tabla.rowCount() >= 1
        celda = win.tabla.cellWidget(0, 0)
        assert celda is not None, "la columna 0 debe llevar un widget (casilla + texto), no un item"
        assert celda.findChild(QCheckBox) is not None
        assert celda.findChild(QLabel) is not None
    finally:
        win.deleteLater()


def test_marcar_casilla_y_pedir_accion_de_carpeta_opera_sobre_todas_las_marcadas(app, entorno_bandeja):
    """Con dos o más casillas marcadas, `_filas_seleccionadas_multiples()` debe devolver TODAS las
    filas marcadas (no solo la fila con foco en la tabla) — la base de la selección múltiple."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        assert win.tabla.rowCount() >= 2, "se esperaban al menos 2 filas en Recibidos para este test"
        for r in range(win.tabla.rowCount()):
            celda = win.tabla.cellWidget(r, 0)
            celda.checkbox.setChecked(True)
        seleccionadas = win._filas_seleccionadas_multiples()
        assert len(seleccionadas) == win.tabla.rowCount()
        claves_esperadas = {(f["tipo"], f["id"]) for f in win._filas}
        claves_obtenidas = {(f["tipo"], f["id"]) for f in seleccionadas}
        assert claves_obtenidas == claves_esperadas
    finally:
        win.deleteLater()


def test_sin_casillas_marcadas_cae_al_comportamiento_de_una_sola_fila_de_siempre(app, entorno_bandeja):
    """Sin ninguna casilla marcada, `_filas_seleccionadas_multiples()` debe comportarse EXACTAMENTE
    como antes de añadir las casillas: la única fila con foco en la tabla (compatibilidad hacia
    atrás con el flujo de selección simple que ya usaban IMPORTANTE/POSPONER/PAPELERA)."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        win.tabla.setCurrentCell(0, 1)
        assert not win._filas_marcadas
        seleccionadas = win._filas_seleccionadas_multiples()
        assert len(seleccionadas) == 1
        assert seleccionadas[0] is win._filas[0]
    finally:
        win.deleteLater()


def test_marcar_la_casilla_no_abre_el_mensaje_pero_clicar_el_texto_si(app, entorno_bandeja):
    """Clicar la casilla SOLO marca/desmarca (no debe disparar la apertura del mensaje); clicar el
    resto de la celda (el texto del remitente) sigue abriendo el mensaje como antes de añadir la
    casilla — mismo comportamiento, sin regresión."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        row_gmail = next(i for i, f in enumerate(win._filas) if f["tipo"] == "gmail")
        celda = win.tabla.cellWidget(row_gmail, 0)

        celda.checkbox.setChecked(True)
        assert _negrita_col0(win.tabla, row_gmail) is True, \
            "marcar la casilla no debe, por sí sola, abrir el mensaje (seguiría negrita/sin leer)"

        celda._on_abrir()   # mismo camino que ejecuta `mousePressEvent` al clicar el texto
        assert _negrita_col0(win.tabla, row_gmail) is False, \
            "clicar el texto del remitente debe seguir abriendo el mensaje, como antes"
    finally:
        win.deleteLater()


def test_accion_importante_con_varias_casillas_marcadas_aplica_a_todas(app, entorno_bandeja):
    """Prueba de extremo a extremo (BD real) de la razón de ser de las casillas: marcar la circular
    Y la encuesta de prueba en Recibidos y pulsar IMPORTANTE (`_accion_importante`) debe marcar
    AMBAS como importantes — no solo la fila con foco, que era el comportamiento de antes."""
    from src.services.comunicacion_interna import circulares, encuestas
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        row_circular = next(i for i, f in enumerate(win._filas) if f["tipo"] == "circular")
        row_encuesta = next(i for i, f in enumerate(win._filas) if f["tipo"] == "encuesta")
        win.tabla.cellWidget(row_circular, 0).checkbox.setChecked(True)
        win.tabla.cellWidget(row_encuesta, 0).checkbox.setChecked(True)
        assert len(win._filas_marcadas) == 2

        win._accion_importante(True)

        u = entorno_bandeja["user"]
        ids_circ_importantes = {c["id"] for c in circulares.listar_importantes(u["id"])}
        ids_enc_importantes = {e["id"] for e in encuestas.listar_importantes(u["id"])}
        assert entorno_bandeja["id_circular"] in ids_circ_importantes
        assert entorno_bandeja["id_encuesta"] in ids_enc_importantes
    finally:
        win.deleteLater()


def test_filas_con_altura_suficiente_para_la_casilla_de_seleccion(app, entorno_bandeja):
    """Bug real reportado: con la altura de fila POR DEFECTO de Qt (~30px), la casilla de
    selección de la columna REMITENTE quedaba cortada por arriba — ahora se fija una altura
    explícita con margen de sobra para casilla + texto."""
    from src.gui.correo_corporativo import CorreoCorporativoWindow
    win = CorreoCorporativoWindow()
    try:
        assert win.tabla.verticalHeader().defaultSectionSize() >= 40
        assert win.tabla.rowHeight(0) >= 40
    finally:
        win.deleteLater()
