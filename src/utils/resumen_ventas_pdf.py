"""
PDF del RESUMEN DE VENTAS (para enviar por el módulo Correo): gráfica de facturación por día + totales
del periodo + top de artículos. Degradable: si faltan matplotlib/reportlab devuelve None (quien llama
informa). No toca datos ni stock.
"""

import logging
import os

logger = logging.getLogger("utils.resumen_ventas_pdf")


def _grafica_png(datos, desde, hasta):
    """Renderiza la serie diaria a PNG (matplotlib Agg, sin Qt). Devuelve bytes PNG o None."""
    try:
        from io import BytesIO

        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
    except Exception as e:
        logger.warning("matplotlib no disponible: %s", e)
        return None
    try:
        fechas = [str(r[0]) for r in datos]
        totales = [float(r[1] or 0) for r in datos]
        fig = Figure(figsize=(8, 3.2), facecolor="white", tight_layout=True)
        ax = fig.add_subplot(111)
        if len(fechas) == 1:
            ax.plot(fechas, totales, color="#00B894", linewidth=2, marker="o")
        else:
            ax.bar(fechas, totales, color="#00B894")
        ax.set_title(f"Facturación  {desde} → {hasta}", fontsize=11)
        step = max(1, len(fechas) // 8)
        ax.set_xticks(range(0, len(fechas), step))
        ax.set_xticklabels(fechas[::step], rotation=30, ha="right", fontsize=7)
        buf = BytesIO()
        FigureCanvasAgg(fig).print_png(buf)
        return buf.getvalue()
    except Exception as e:
        logger.error("_grafica_png: %s", e)
        return None


def generar_resumen_ventas_pdf(datos, top10, desde, hasta, archivo, *, filtros=None):
    """Genera el PDF del resumen. `datos`=[(dia,total)], `top10`=[(cod,nombre,uds)]. Devuelve ruta o None."""
    try:
        from io import BytesIO

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as _canvas
    except Exception as e:
        logger.warning("reportlab no disponible: %s", e)
        return None
    try:
        os.makedirs(os.path.dirname(archivo), exist_ok=True)
        ancho, alto = A4
        c = _canvas.Canvas(archivo, pagesize=A4)
        cyan = (0.0, 0.72, 0.58)
        y = alto - 22 * mm
        c.setFillColorRGB(*cyan); c.setFont("Helvetica-Bold", 16)
        c.drawString(20 * mm, y, "Resumen de ventas")
        y -= 8 * mm
        c.setFillColorRGB(0.3, 0.3, 0.3); c.setFont("Helvetica", 10)
        c.drawString(20 * mm, y, f"Periodo: {desde} → {hasta}")
        if filtros:
            y -= 5 * mm
            c.drawString(20 * mm, y, filtros)
        y -= 6 * mm

        total_periodo = sum(float(r[1] or 0) for r in (datos or []))
        c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, f"Total del periodo: {total_periodo:,.2f} €")
        y -= 4 * mm

        # Gráfica
        png = _grafica_png(datos or [], desde, hasta)
        if png:
            img = ImageReader(BytesIO(png))
            iw = ancho - 40 * mm
            ih = iw * 0.40
            y -= ih + 4 * mm
            c.drawImage(img, 20 * mm, y, iw, ih, preserveAspectRatio=True, mask="auto")

        # Detalle por día
        y -= 8 * mm
        c.setFillColorRGB(*cyan); c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, "Ventas por día"); y -= 6 * mm
        c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica", 9)
        for dia, total in (datos or [])[:24]:
            if y < 40 * mm:
                c.showPage(); y = alto - 22 * mm
                c.setFont("Helvetica", 9)
            c.drawString(24 * mm, y, f"{dia}")
            c.drawRightString(ancho - 22 * mm, y, f"{float(total or 0):,.2f} €")
            y -= 5 * mm

        # Top artículos
        if top10:
            y -= 4 * mm
            if y < 50 * mm:
                c.showPage(); y = alto - 22 * mm
            c.setFillColorRGB(*cyan); c.setFont("Helvetica-Bold", 11)
            c.drawString(20 * mm, y, "Top artículos vendidos"); y -= 6 * mm
            c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica", 9)
            for cod, nombre, uds in top10:
                if y < 25 * mm:
                    c.showPage(); y = alto - 22 * mm
                    c.setFont("Helvetica", 9)
                c.drawString(24 * mm, y, f"{(nombre or cod)}"[:60])
                c.drawRightString(ancho - 22 * mm, y, f"{int(uds)} uds")
                y -= 5 * mm

        c.showPage(); c.save()
        return archivo
    except Exception as e:
        logger.error("generar_resumen_ventas_pdf: %s", e)
        return None
