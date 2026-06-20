"""Render documental RRHH `render_certificado` (F3.0.4b).

Cuerpo VERBATIM extraído de `_WizardDocumentoFiscal._generar_pdf` (closure
`_pdf_certificado` de F3.0.4a). Los nombres libres se resuelven desde `ctx` (scope del
wizard) inyectado por `contexto.ejecutar`. NO se modifica una sola línea de lógica.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        subtipo_label = subtipo or "EMPRESA"
        story.append(_sec_header("CERTIFICADO LABORAL — " + subtipo_label))
        story.append(Spacer(1, 2*mm))
        story.append(_P(
            f"D./Dña. _________________________, en calidad de representante legal de "
            f"<b>{emp_nombre}</b> (CIF: {emp_cif}), con domicilio en {emp_dir},",
            st_body
        ))
        story.append(Spacer(1, 2*mm))
        story.append(_P("<b>CERTIFICA:</b>", st_h2))
        story.append(Spacer(1, 1*mm))
        cert_body = {
            "VIDA LABORAL": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}, Nº SS: {ss or '—'}), ha mantenido "
                f"relación laboral con esta empresa, constando su alta en la Seguridad Social "
                f"a efectos de {fecha}. El presente certificado se expide a petición del/de la "
                f"interesado/a para los fines que estime conveniente."
            ),
            "COTIZACIÓN": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}), figura en los registros de cotización "
                f"de esta empresa como trabajador/a en alta. El salario bruto mensual es de "
                f"{divisas.formatear(salario_mensual)} con las retenciones de IRPF y cotizaciones a la "
                f"Seguridad Social que legalmente corresponden."
            ),
            "EMPRESA": (
                f"Que los datos de la empresa <b>{emp_nombre}</b> son correctos y están "
                f"debidamente registrados en las administraciones competentes. "
                f"CIF: {emp_cif}. IBAN: {emp_iban or '—'}. "
                f"Tel: {emp_tel or '—'}. Email: {emp_email or '—'}."
            ),
        }.get(subtipo_label,
              f"Los datos del/de la trabajador/a {trab} son verídicos según los registros internos.")
        story.append(_P(cert_body, st_body))
        if obs:
            story.append(Spacer(1, 3*mm))
            story.append(_P(obs, st_body))
        story.append(Spacer(1, 5*mm))
        story.append(_P(
            f"Y para que así conste y surta los efectos oportunos, se expide el presente "
            f"certificado en {emp_dir or '_______________'} a {_fecha_larga(now)}.",
            st_body
        ))



def render_certificado(ctx):
    ejecutar(_impl, ctx)
