"""Render documental RRHH `render_alta_baja` (F3.0.4b).

Cuerpo VERBATIM extraído de `_WizardDocumentoFiscal._generar_pdf` (closure
`_pdf_alta_baja` de F3.0.4a). Los nombres libres se resuelven desde `ctx` (scope del
wizard) inyectado por `contexto.ejecutar`. NO se modifica una sola línea de lógica.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        accion = "ALTA" if self._tipo == "ALTA" else "BAJA"
        story.append(_sec_header(f"COMUNICACIÓN DE {accion} LABORAL EN SEGURIDAD SOCIAL"))
        story.append(Spacer(1, 1*mm))
        story.append(_sec_header("DATOS DEL EMPLEADOR"))
        story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
        story.append(_data_val_row(("CCC", emp_ccc or "—"), ("DOMICILIO", emp_dir)))
        story.append(Spacer(1, 1*mm))
        story.append(_sec_header("DATOS DEL TRABAJADOR/A"))
        story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif)))
        story.append(_data_val_row(("Nº SEG. SOCIAL", ss or "—"), ("FECHA EFECTO", fecha)))
        story.append(Spacer(1, 3*mm))
        story.append(_P(
            f"Se comunica el <b>{accion} LABORAL</b> en la Seguridad Social de "
            f"<b>{trab}</b> (NIF/NIE: {nif}), con efectos desde el <b>{fecha}</b>, "
            f"en la empresa <b>{emp_nombre}</b> (CIF: {emp_cif}), conforme a la "
            f"Ley General de la Seguridad Social (RDL 8/2015) y normativa vigente.",
            st_body
        ))
        if obs:
            story.append(Spacer(1, 3*mm))
            story.append(_P(f"<b>Observaciones:</b> {obs}", st_body))



def render_alta_baja(ctx):
    ejecutar(_impl, ctx)
