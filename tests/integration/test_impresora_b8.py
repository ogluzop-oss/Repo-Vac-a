"""BLOQUE 8.4 — adaptadores de impresora (sin hardware): validación y degradación."""
from src.services.perifericos import impresora as I


def test_config_usb_requiere_ids():
    ok, msg = I.ImpresoraConfig(conexion=I.USB).valida()
    assert ok is False and "vendor_id" in msg
    ok, _ = I.ImpresoraConfig(conexion=I.USB, vendor_id=0x04B8, product_id=0x0202).valida()
    assert ok is True


def test_config_red_requiere_host():
    ok, msg = I.ImpresoraConfig(conexion=I.RED).valida()
    assert ok is False and "host" in msg
    assert I.ImpresoraConfig(conexion=I.RED, host="192.168.1.50").valida()[0] is True


def test_config_serie_bluetooth_requiere_dispositivo():
    assert I.ImpresoraConfig(conexion=I.BLUETOOTH).valida()[0] is False
    assert I.ImpresoraConfig(conexion=I.SERIE, dispositivo="COM3").valida()[0] is True


def test_conexion_no_soportada():
    assert I.ImpresoraConfig(conexion="laser").valida()[0] is False


def test_imprimir_degrada_sin_backend(monkeypatch):
    # Config válida pero forzamos que no haya backend/hardware -> no lanza, devuelve False.
    cfg = I.ImpresoraConfig(conexion=I.RED, host="10.0.0.1")
    monkeypatch.setattr(I, "_crear_printer", lambda c: (_ for _ in ()).throw(RuntimeError("sin device")))
    ok, msg = I.imprimir_lineas(["Ticket"], cfg)
    assert ok is False and "no disponible" in msg


def test_imprimir_config_invalida():
    ok, msg = I.imprimir_lineas(["x"], I.ImpresoraConfig(conexion=I.USB))
    assert ok is False and "inválida" in msg.lower()


def test_estado_certificacion():
    e = I.estado_certificacion()
    assert e["estado"] == "PREPARADO PARA VALIDACIÓN"
    assert "epson" in e["fabricantes"] and "star" in e["fabricantes"]
    assert set(e["conexiones"]) == {I.USB, I.BLUETOOTH, I.RED, I.SERIE}
    assert "escpos" in e["backends_disponibles"]
