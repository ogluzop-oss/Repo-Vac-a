"""
Ventana de Facturación del TPV: regla de negocio (no facturar sin cliente registrado)
y generación correcta. Usa QApplication offscreen + mocks de la capa de datos.
Vive en la suite completa (importa GUI con deps completas).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _montar(monkeypatch, ventas, completa):
    from src.gui import factura_window as FW
    monkeypatch.setattr(FW.VB, "buscar_ventas", lambda **k: ventas)
    monkeypatch.setattr(FW.VB, "obtener_venta_completa", lambda vid: completa)
    monkeypatch.setattr(FW.fiscalidad, "desglose_iva",
                        lambda total, **k: {"tipo": 21, "base": 10.0, "cuota": 2.1, "total": total})
    monkeypatch.setattr(FW, "mostrar_mensaje", lambda *a, **k: None)
    monkeypatch.setattr(FW.factura_pdf, "generar_y_registrar", lambda *a, **k: None)
    monkeypatch.setattr(FW.FC, "obtener_factura", lambda fid, **k: {"numero": f"FC{fid:06d}"})
    w = FW.FacturaWindow(usuario={"id": 1})
    return FW, w


_VENTA = {"id": 10, "fecha": "2026-01-01 10:00", "total": 12.1, "forma_pago": "efectivo",
          "empleado": "A", "numero_caja": 1, "cliente_nombre": None, "n_items": 1}
_COMPLETA = {"id": 10, "total": 12.1, "cliente_nif": None, "cliente_nombre": None,
             "items": [{"codigo_articulo": "X", "nombre": "Art", "cantidad": 1,
                        "precio_unitario": 12.1, "subtotal": 12.1}]}


def test_bloquea_factura_sin_cliente(app, monkeypatch):
    FW, w = _montar(monkeypatch, [dict(_VENTA)], dict(_COMPLETA))
    monkeypatch.setattr(FW.CLI, "buscar_clientes", lambda *a, **k: [])
    # El popup de selección se cancela -> NO debe facturar.
    monkeypatch.setattr(FW._SelectorClienteDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    llamadas = {"n": 0}
    monkeypatch.setattr(FW.FC, "crear_factura", lambda **k: llamadas.__setitem__("n", llamadas["n"] + 1) or 99)
    w.tabla.selectRow(0)
    w._generar_factura()
    assert llamadas["n"] == 0  # regla de negocio: bloqueado sin cliente registrado


def test_genera_con_cliente_ya_asignado(app, monkeypatch):
    venta = dict(_VENTA, id=11, cliente_nombre="Moha")
    completa = dict(_COMPLETA, id=11, cliente_nif="B8320921", cliente_nombre="Moha")
    FW, w = _montar(monkeypatch, [venta], completa)
    monkeypatch.setattr(FW.CLI, "buscar_clientes",
                        lambda *a, **k: [{"id": 7, "nombre": "Moha", "nif": "B8320921"}])
    cap = {}
    monkeypatch.setattr(FW.FC, "crear_factura", lambda **k: cap.update(k) or 123)
    w.tabla.selectRow(0)
    w._generar_factura()
    assert cap.get("id_cliente") == 7 and cap.get("id_venta") == 11
    assert cap.get("base") == 10.0 and cap.get("iva") == 2.1


def test_genera_tras_seleccionar_cliente_en_popup(app, monkeypatch):
    FW, w = _montar(monkeypatch, [dict(_VENTA)], dict(_COMPLETA))
    monkeypatch.setattr(FW.CLI, "buscar_clientes", lambda *a, **k: [])
    monkeypatch.setattr(FW.VB, "asignar_cliente_venta", lambda *a, **k: True)

    def _fake_exec(self):
        self.cliente = {"id": 5, "nombre": "Nuevo", "nif": "12345678Z"}
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(FW._SelectorClienteDialog, "exec", _fake_exec)
    cap = {}
    monkeypatch.setattr(FW.FC, "crear_factura", lambda **k: cap.update(k) or 200)
    w.tabla.selectRow(0)
    w._generar_factura()
    assert cap.get("id_cliente") == 5 and cap.get("id_venta") == 10
