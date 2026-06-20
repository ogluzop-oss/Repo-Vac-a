"""Render documental RRHH `render_generico` (F3.0.4b).

Cuerpo VERBATIM extraído de `_WizardDocumentoFiscal._generar_pdf` (closure
`_pdf_generico` de F3.0.4a). Los nombres libres se resuelven desde `ctx` (scope del
wizard) inyectado por `contexto.ejecutar`. NO se modifica una sola línea de lógica.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        story.append(_P(
            obs or f"Documento generado por Smart Manager — Ref: {doc_id}", st_body))



def render_generico(ctx):
    ejecutar(_impl, ctx)
