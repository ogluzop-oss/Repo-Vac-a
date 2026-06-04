# src/utils/reportes_safebag.py
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ============================================================
# BLOQUE GENERACIÓN DE INFORME SAFEBAG EN PDF
# ============================================================

def generar_safebag_pdf(path_destino, safebag_record):
    """
    Genera el PDF de cierre de caja SafeBag.

    safebag_record espera las claves:
        empresa, tienda, fecha, referencia,
        billetes_total, monedas_total, importe_total,
        empleado, notas
    """
    os.makedirs(os.path.dirname(path_destino), exist_ok=True)
    c = canvas.Canvas(path_destino, pagesize=A4)
    w, h = A4

    margin = 20 * mm
    x = margin
    y = h - margin

    # --- Encabezado ---
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, safebag_record.get("empresa", "Empresa"))
    c.setFont("Helvetica", 10)
    c.drawString(x, y - 16, f"Tienda: {safebag_record.get('tienda', '-')}")
    c.drawString(x, y - 32, f"Fecha: {safebag_record.get('fecha', datetime.now().isoformat())}")
    c.drawString(x, y - 48, f"Referencia SafeBag: {safebag_record.get('referencia', '-')}")
    c.line(x, y - 58, w - margin, y - 58)

    # --- Detalle billetes/monedas ---
    y = y - 80
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Detalle SafeBag")
    c.setFont("Helvetica", 10)
    y -= 18
    c.drawString(x, y, f"Total billetes: {safebag_record.get('billetes_total', 0):.2f} €")
    y -= 14
    c.drawString(x, y, f"Total monedas:   {safebag_record.get('monedas_total', 0):.2f} €")
    y -= 14
    c.drawString(x, y, f"Importe total:   {safebag_record.get('importe_total', 0):.2f} €")
    y -= 24
    c.drawString(x, y, f"Empleado: {safebag_record.get('empleado', '-')}")
    y -= 14
    c.drawString(x, y, f"Notas: {safebag_record.get('notas', '')}")
    y -= 40

    # --- Pie ---
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(x, y, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.save()
    return path_destino


# ============================================================
# BLOQUE EJEMPLO DE USO (EJECUCIÓN DIRECTA)
# ============================================================

if __name__ == "__main__":
    record = {
        "empresa":        "MiEmpresa SL",
        "tienda":         "Tienda Centro",
        "fecha":          "2025-10-31",
        "referencia":     "SB-2025-1031-001",
        "billetes_total": 1200.00,
        "monedas_total":  35.50,
        "importe_total":  1235.50,
        "empleado":       "Juan Perez",
        "notas":          "Arqueo diario",
    }
    folder   = "Documentos/Informe_SafeBag/2025/10/31"
    filename = f"{folder}/{record['referencia']}.pdf"
    generar_safebag_pdf(filename, record)
    print("PDF creado:", filename)
