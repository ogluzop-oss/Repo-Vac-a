"""Render documental RRHH `render_carta_despido` (F3.0.4b).

Cuerpo VERBATIM extraído de `_WizardDocumentoFiscal._generar_pdf` (closure
`_pdf_carta_despido` de F3.0.4a). Los nombres libres se resuelven desde `ctx` (scope del
wizard) inyectado por `contexto.ejecutar`. NO se modifica una sola línea de lógica.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        subtipo_label = subtipo or "DISCIPLINARIO"
        story.append(_sec_header("DATOS DE LA EMPRESA COMUNICANTE"))
        story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
        story.append(_data_val_row(("DOMICILIO", emp_dir)))
        story.append(Spacer(1, 1*mm))
        story.append(_sec_header("DATOS DE LA PERSONA TRABAJADORA"))
        story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif)))
        story.append(_data_val_row(("PUESTO", puesto or "—"), ("FECHA EFECTO", fecha)))
        story.append(Spacer(1, 3*mm))
        story.append(_P(
            f"{emp_dir or '—'},  a {_fecha_larga(now)}",
            st_right
        ))
        story.append(Spacer(1, 2*mm))
        story.append(_P(f"Estimado/a Sr./Sra. {trab}:", st_body))
        story.append(Spacer(1, 2*mm))
        intro_map = {
            "DISCIPLINARIO": (
                "Por medio de la presente, y en virtud de lo establecido en el artículo 54 "
                "del Estatuto de los Trabajadores (RDL 2/2015), la dirección de la empresa "
                f"le comunica la decisión de proceder a su <b>despido disciplinario</b>, "
                f"con efectos desde el día <b>{fecha}</b>, por incumplimiento grave y culpable "
                "de sus obligaciones laborales, en concreto por las causas que a continuación se detallan:"
            ),
            "OBJETIVO": (
                "Por medio de la presente, y al amparo de lo previsto en el artículo 52 del "
                "Estatuto de los Trabajadores, la empresa le notifica la extinción de su "
                f"contrato de trabajo por <b>causas objetivas</b>, con efectos desde el día "
                f"<b>{fecha}</b>. Tiene derecho a la indemnización legalmente establecida "
                "de <b>20 días de salario por año de servicio</b>, prorrateándose los períodos "
                "inferiores a un año."
            ),
            "IMPROCEDENTE": (
                "La empresa reconoce el carácter <b>improcedente</b> del despido con efectos "
                f"desde el día <b>{fecha}</b>, y le comunica la indemnización de "
                "<b>33 días de salario por año de servicio</b> desde el 12/02/2012, "
                "o de 45 días por los períodos anteriores (máximo 720 días de salario)."
            ),
        }
        story.append(_P(intro_map.get(subtipo_label,
            f"Se le comunica la extinción de su relación laboral con efectos desde el {fecha}."), st_body))
        if articulo_et:
            story.append(Spacer(1, 2*mm))
            story.append(_P(f"<b>PRECEPTO LEGAL INVOCADO:</b> {articulo_et}", st_body))
        if obs:
            story.append(Spacer(1, 2*mm))
            story.append(_sec_header("HECHOS Y FUNDAMENTOS"))
            story.append(Spacer(1, 1*mm))
            story.append(_P(obs, st_clause))
        story.append(Spacer(1, 3*mm))
        story.append(_P(
            "Se le informa de su derecho a impugnar esta decisión ante el Juzgado de lo Social "
            "competente en el plazo de <b>20 días hábiles</b> desde la notificación, previa "
            "presentación de papeleta de conciliación ante el SMAC u organismo competente.",
            st_body
        ))
        story.append(Spacer(1, 2*mm))
        story.append(_P(f"Atentamente,<br/><b>{emp_nombre}</b>", st_body))



def render_carta_despido(ctx):
    ejecutar(_impl, ctx)
