# src/utils/impresion.py
"""
Módulo para impresión de tickets usando reportlab y escpos.
"""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import os
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


def generar_ticket_pdf(datos: Dict, archivo: str = "ticket.pdf"):
    """Genera un ticket en PDF."""
    c = canvas.Canvas(archivo, pagesize=(3 * inch, 4 * inch))  # Tamaño ticket
    c.setFont("Helvetica", 10)

    y = 3.5 * inch
    c.drawString(0.2 * inch, y, "SMART MANAGER AI")
    y -= 0.3 * inch
    c.drawString(0.2 * inch, y, f"Fecha: {datos.get('fecha', 'N/A')}")
    y -= 0.3 * inch
    for item in datos.get("items", []):
        c.drawString(
            0.2 * inch, y, f"{item['nombre']} x{item['cantidad']} - ${item['precio']}"
        )
        y -= 0.2 * inch

    c.drawString(0.2 * inch, y, f"Total: ${datos.get('total', 0)}")
    c.save()
    logger.info(f"Ticket generado: {archivo}")


def imprimir_ticket_termico(datos: Dict):
    """Imprime ticket en impresora térmica."""
    try:
        from escpos.printer import Usb

        printer = Usb(0x04B8, 0x0202)  # ID de Epson, ajustar según impresora
        printer.set(align="center", font="a", bold=True, width=2, height=2)
        printer.text("SMART MANAGER AI\n")
        printer.set(align="left")
        printer.text(f"Fecha: {datos.get('fecha')}\n")
        for item in datos.get("items", []):
            printer.text(f"{item['nombre']} x{item['cantidad']} ${item['precio']}\n")
        printer.text(f"Total: ${datos.get('total')}\n")
        printer.cut()
        printer.close()
        logger.info("Ticket impreso en térmica.")
    except Exception as e:
        logger.error(f"Error imprimiendo térmica: {e}")
