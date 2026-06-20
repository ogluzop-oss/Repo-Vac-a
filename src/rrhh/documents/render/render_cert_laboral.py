"""
Render documental RRHH `render_cert_laboral` (F4.2).

Plantilla dedicada del CERTIFICADO LABORAL (deja de usar `render_generico`). Genera un
certificado diferenciado por subtipo (GENERAL/INGRESOS/ANTIGÜEDAD/FUNCIONES/JORNADA/
VACACIONES) sobre el cuerpo del documento; el epílogo del wizard añade observaciones,
firmas, pie y hash (compartido). Nombres libres resueltos desde `ctx` (scope del wizard)
vía `contexto.ejecutar`, igual que el resto de renders RRHH. Sin lógica de negocio ni
persistencia nuevas: solo presentación.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        subtipo_label = subtipo or "GENERAL"
        story.append(_sec_header("CERTIFICADO LABORAL — " + subtipo_label))
        story.append(Spacer(1, 2*mm))
        story.append(_P(
            f"D./Dña. {rep_nombre_full or '_________________________'}, en calidad de "
            f"{rep_cargo or 'representante legal'} de <b>{emp_nombre}</b> (CIF: {emp_cif}), "
            f"con domicilio en {emp_dir or '—'},",
            st_body
        ))
        story.append(Spacer(1, 2*mm))
        story.append(_P("<b>CERTIFICA:</b>", st_h2))
        story.append(Spacer(1, 1*mm))

        _puesto = self._datos.get("puesto") or puesto or "—"
        _antig = self._datos.get("antiguedad") or self._datos.get("fecha") or fecha
        _func = self._datos.get("funciones") or funciones or "las propias de su puesto"
        _jornada = self._datos.get("tipo_jornada") or "completa"
        _horas = self._datos.get("horas_semanales") or "40"
        _vac_dias = self._datos.get("vacaciones_dias") or self._datos.get("vacaciones") or "30"

        cuerpos = {
            "GENERAL": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}, Nº S.S.: {ss or '—'}) presta servicios en "
                f"esta empresa con la categoría/puesto de <b>{_puesto}</b>, manteniendo una "
                f"relación laboral en vigor a fecha de {fecha}."
            ),
            "INGRESOS": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}) percibe de esta empresa un salario bruto "
                f"mensual de <b>{divisas.formatear(salario_mensual)}</b>, con las retenciones de "
                f"IRPF y cotizaciones a la Seguridad Social que legalmente correspondan."
            ),
            "ANTIGÜEDAD": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}) mantiene relación laboral con esta empresa "
                f"con una antigüedad reconocida desde {_antig}, ocupando el puesto de <b>{_puesto}</b>."
            ),
            "FUNCIONES": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}) desempeña en esta empresa el puesto de "
                f"<b>{_puesto}</b>, cuyas funciones principales son: {_func}."
            ),
            "JORNADA": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}) está contratado/a con jornada <b>{_jornada}</b>, "
                f"con una dedicación de {_horas} horas semanales, en el puesto de {_puesto}."
            ),
            "VACACIONES": (
                f"Que <b>{trab}</b> (NIF/NIE: {nif}) tiene reconocido un periodo de vacaciones "
                f"anuales de <b>{_vac_dias} días</b> según el convenio de aplicación "
                f"({self._datos.get('convenio') or convenio or '—'})."
            ),
        }
        story.append(_P(cuerpos.get(subtipo_label, cuerpos["GENERAL"]), st_body))
        story.append(Spacer(1, 5*mm))
        story.append(_P(
            f"Y para que así conste y surta los efectos oportunos a petición del/de la "
            f"interesado/a, se expide el presente certificado en {emp_municipio or emp_dir or '_______________'} "
            f"a {_fecha_larga(now)}.",
            st_body
        ))


def render_cert_laboral(ctx):
    ejecutar(_impl, ctx)
