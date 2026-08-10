"""
Portal Web · BUSCADOR GLOBAL unificado (Fase WEB-10).

Localiza en un único punto clientes · artículos · pedidos · reservas · encargos REUTILIZANDO los
buscadores/listados existentes (`db.clientes`, `db.articulos`, `online_orders_service`). No implementa
búsqueda propia sobre BD: agrega resultados de los servicios existentes. Solo presentación; degradable.
"""

from PyQt6.QtWidgets import QLabel

from src.gui._neon_ui import _CIAN, _TEXT2
from src.gui.portal_web_ui.componentes import (Buscador, PanelSeccion,
                                               PanelTabla)


def _match(texto, *valores):
    t = (texto or "").lower()
    return any(t in str(v or "").lower() for v in valores)


class SeccionBuscadorGlobal(PanelSeccion):
    def __init__(self, parent=None):
        super().__init__("Buscador global", "🔎", parent)
        self.breadcrumb.set_ruta(["Portal Web", "Buscador global"])
        self._buscador = Buscador("Buscar clientes, artículos, pedidos, reservas, encargos…")
        self._buscador.buscar.connect(self._buscar)
        self.cuerpo.addWidget(self._buscador)
        self._info = QLabel("Introduce un término para buscar en todo el Portal Web.")
        self._info.setStyleSheet(f"color:{_TEXT2};font-size:12px;")
        self.cuerpo.addWidget(self._info)
        self.panel = PanelTabla(nombre_export="portal_web_busqueda")
        self.cuerpo.addWidget(self.panel, 1)

    def _buscar(self, texto):
        texto = (texto or "").strip()
        if not texto:
            self.panel.cargar(["—"], [])
            self._info.setText("Introduce un término para buscar en todo el Portal Web.")
            return
        filas = []
        filas += self._clientes(texto)
        filas += self._articulos(texto)
        filas += self._pedidos(texto)
        filas += self._reservas(texto)
        self.panel.cargar(["tipo", "id", "descripcion", "detalle"], filas)
        self._info.setText(f"{len(filas)} resultado(s) para «{texto}».")

    def _clientes(self, texto):
        try:
            from src.db import clientes as C
            return [{"tipo": "Cliente", "id": r.get("id") or r.get("codigo"),
                     "descripcion": r.get("nombre"), "detalle": r.get("nif") or r.get("email") or ""}
                    for r in (C.buscar_clientes(texto) or [])][:50]
        except Exception:
            return []

    def _articulos(self, texto):
        try:
            from src.db import articulos as A
            arts = A.obtener_articulos() or []
            out = []
            for a in arts:
                cod = a.get("codigo") if isinstance(a, dict) else (a[0] if a else None)
                nom = a.get("nombre") if isinstance(a, dict) else (a[1] if len(a) > 1 else None)
                if _match(texto, cod, nom):
                    out.append({"tipo": "Artículo", "id": cod, "descripcion": nom, "detalle": ""})
            return out[:50]
        except Exception:
            return []

    def _pedidos(self, texto):
        try:
            from src.services.tpv import online_orders_service as OS
            return [{"tipo": "Pedido", "id": p.get("id_pedido") or p.get("id"),
                     "descripcion": p.get("cliente") or p.get("nombre_cliente") or "",
                     "detalle": p.get("estado") or ""}
                    for p in (OS.listar_pedidos_online() or [])
                    if _match(texto, p.get("id_pedido"), p.get("id"), p.get("cliente"),
                              p.get("referencia_externa"))][:50]
        except Exception:
            return []

    def _reservas(self, texto):
        try:
            from src.services.tpv import online_orders_service as OS
            out = []
            for r in (OS.listar_reservas() or []):
                if _match(texto, r.get("codigo_articulo"), r.get("cliente"), r.get("id"),
                          r.get("observaciones")):
                    tipo = "Encargo" if str(r.get("tipo")) == "ENCARGO" else "Reserva"
                    out.append({"tipo": tipo, "id": r.get("id"),
                                "descripcion": f"{r.get('codigo_articulo') or ''} · {r.get('cliente') or ''}",
                                "detalle": r.get("estado") or ""})
            return out[:50]
        except Exception:
            return []
