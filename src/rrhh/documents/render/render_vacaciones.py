"""
Render documental RRHH `render_vacaciones` (F4.2).

Plantilla dedicada de VACACIONES (deja de usar `render_generico`), diferenciada por
subtipo (SOLICITUD/APROBACIÓN/DENEGACIÓN). Incluye trabajador, fechas, días, empresa y
centro; el epílogo del wizard añade observaciones, firmas, pie y hash (compartido).
Nombres libres resueltos desde `ctx` (scope del wizard) vía `contexto.ejecutar`. Sin
lógica de negocio ni persistencia nuevas: solo presentación.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        subtipo_label = subtipo or "SOLICITUD"
        f_ini = fecha
        f_fin = self._datos.get("fecha_fin_vac") or "—"
        responsable = self._datos.get("responsable") or "—"
        motivo = self._datos.get("motivo_baja") or ""
        centro = self._datos.get("centro_trabajo") or ct_nombre or "—"
        # Nº de días (ambos inclusive) si las fechas son parseables; si no, "—".
        dias = "—"
        try:
            _di = datetime.strptime(str(f_ini), "%d/%m/%Y")
            _df = datetime.strptime(str(f_fin), "%d/%m/%Y")
            dias = str((_df - _di).days + 1)
        except Exception:
            dias = self._datos.get("vacaciones_dias") or "—"

        titulos = {
            "SOLICITUD": "SOLICITUD DE VACACIONES",
            "APROBACIÓN": "APROBACIÓN DE VACACIONES",
            "DENEGACIÓN": "DENEGACIÓN DE VACACIONES",
        }
        story.append(_sec_header(titulos.get(subtipo_label, "VACACIONES")))
        story.append(Spacer(1, 2*mm))
        story.append(_data_val_row(("TRABAJADOR/A", trab), ("NIF/NIE", nif)))
        story.append(_data_val_row(("EMPRESA", emp_nombre), ("CIF", emp_cif)))
        story.append(_data_val_row(("CENTRO DE TRABAJO", centro)))
        story.append(_data_val_row(("FECHA INICIO", f_ini), ("FECHA FIN", f_fin),
                                   ("Nº DÍAS", dias)))
        story.append(Spacer(1, 3*mm))

        if subtipo_label == "SOLICITUD":
            cuerpo = (
                f"El/La trabajador/a <b>{trab}</b> solicita el disfrute de su período de "
                f"vacaciones desde el <b>{f_ini}</b> hasta el <b>{f_fin}</b> (total: {dias} días), "
                f"quedando a la espera de la conformidad de la empresa <b>{emp_nombre}</b>."
            )
        elif subtipo_label == "APROBACIÓN":
            cuerpo = (
                f"La empresa <b>{emp_nombre}</b> <b>APRUEBA</b> el período de vacaciones solicitado "
                f"por <b>{trab}</b>, comprendido entre el <b>{f_ini}</b> y el <b>{f_fin}</b> "
                f"(total: {dias} días). Responsable que autoriza: {responsable}."
            )
        else:  # DENEGACIÓN
            cuerpo = (
                f"La empresa <b>{emp_nombre}</b> comunica la <b>DENEGACIÓN</b> del período de "
                f"vacaciones solicitado por <b>{trab}</b> (del {f_ini} al {f_fin}). "
                f"Motivo: {motivo or 'necesidades organizativas del servicio'}. "
                f"Responsable: {responsable}."
            )
        story.append(_P(cuerpo, st_body))
        story.append(Spacer(1, 5*mm))
        story.append(_P(
            f"Documento emitido en {emp_municipio or emp_dir or '_______________'} "
            f"a {_fecha_larga(now)}.",
            st_body
        ))


def render_vacaciones(ctx):
    ejecutar(_impl, ctx)
