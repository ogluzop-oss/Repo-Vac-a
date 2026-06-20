"""Render documental RRHH `render_contrato` (F3.0.4b).

Cuerpo VERBATIM extraído de `_WizardDocumentoFiscal._generar_pdf` (closure
`_pdf_contrato` de F3.0.4a). Los nombres libres se resuelven desde `ctx` (scope del
wizard) inyectado por `contexto.ejecutar`. NO se modifica una sola línea de lógica.
"""

from src.rrhh.documents.render.contexto import ejecutar


def _impl():
        subtipo_label    = subtipo or "INDEFINIDO"
        _puesto_txt      = puesto or "Según categoría profesional"
        _grupo_txt       = grupo_prof or "Según convenio"
        _func_txt        = funciones or "Las propias del grupo profesional"
        _centro_txt      = (centro_trabajo
                            or ", ".join(x for x in [ct_nombre, ct_dir, ct_municipio] if x)
                            or emp_dir or "—")
        _horas_txt       = horas_sem or "40"
        _dist_txt        = distribucion or "Lunes a domingo"
        _prueba_txt      = periodo_prueba or "Conforme a convenio colectivo"
        _vac_txt         = vacaciones or "Según Convenio"
        _conv_txt        = convenio or "el aplicable al sector de actividad"
        _jornada_parcial = tipo_jornada == "TIEMPO PARCIAL"
        _distancia_si    = trabajo_distancia == "SÍ"
        _sal_mensual_fmt = f"{divisas.formatear(salario_mensual)}" if salario_mensual > 0 else "—"
        _sal_anual_fmt   = f"{divisas.formatear(salario)}" if salario > 0 else "—"

        # ── Modalidad contractual: determina cláusulas y código dinámicos ──
        _sub_norm    = (subtipo or "INDEFINIDO").upper()
        _es_fijodisc = "FIJO" in _sub_norm
        _es_sustit   = "SUSTITU" in _sub_norm
        _es_practic  = "CTIC" in _sub_norm                 # PRÁCTICAS / PRACTICAS
        _es_temporal = "TEMPORAL" in _sub_norm or _es_sustit
        _es_determinada = _es_temporal or _es_practic      # duración determinada (no indefinida)
        _fecha_fin   = self._datos.get("fecha_fin", "")

        # Los logos institucionales van en la cabecera de CADA página
        # (_draw_header), no en el cuerpo.
        # Banner del título (modelo SEPE) — barra sombreada a ancho completo.
        _tb = Table([[Paragraph(titulo_doc, _st("tbanner", fontName=_FB, fontSize=12,
                                                 textColor=AZUL, leading=15))]],
                    colWidths=[usable_w])
        _tb.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), HexColor("#E9EEF6")),
            ("BOX", (0,0), (-1,-1), 0.6, AZUL),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
        ]))
        story.append(_tb)
        story.append(Spacer(1, 2.5*mm))
        story.append(_sec_header("DATOS DE LA EMPRESA"))
        story.append(_data_val_row(("CIF/NIF/NIE", emp_cif)))
        story.append(_data_val_row(
            ("D./DÑA. (REPRESENTANTE LEGAL)", rep_nombre_full or "—"),
            ("NIF/NIE", rep_nif or "—"),
        ))
        story.append(_data_val_row(("EN CONCEPTO", rep_cargo or "REPRESENTANTE LEGAL")))
        story.append(_data_val_row(("NOMBRE O RAZÓN SOCIAL DE LA EMPRESA", emp_nombre)))
        story.append(_data_val_row(("DOMICILIO SOCIAL", emp_dir)))
        story.append(_data_val_row(
            ("MUNICIPIO", _vc(emp_municipio, emp_cod_muni)),
            ("PROVINCIA", _vc(emp_provincia, emp_cod_prov)),
            ("CÓDIGO POSTAL", emp_cp or "—"),
            ("PAÍS", _vc(emp_pais, emp_cod_pais)),
        ))
        story.append(Spacer(1, 1*mm))

        story.append(_sec_header("DATOS DE LA CUENTA DE COTIZACIÓN"))
        story.append(_data_val_row(
            ("RÉGIMEN", emp_regimen or "0111"),
            ("CÓDIGO CUENTA DE COTIZACIÓN", emp_ccc or "—"),
        ))
        story.append(_data_val_row(
            ("ACTIVIDAD ECONÓMICA", _vc(emp_actividad, emp_cod_act)),
            ("CNAE", emp_cnae or "—"),
        ))
        story.append(Spacer(1, 1*mm))

        story.append(_sec_header("DATOS DEL CENTRO DE TRABAJO"))
        if ct_nombre or ct_dir:
            story.append(_data_val_row(("CENTRO DE TRABAJO", ct_nombre or "—"),
                                       ("CÓD. CENTRO", ct_codigo or "—")))
            story.append(_data_val_row(("DOMICILIO", ct_dir or "—")))
            story.append(_data_val_row(
                ("MUNICIPIO", _vc(ct_municipio or emp_municipio, ct_cod_muni or emp_cod_muni)),
                ("PROVINCIA", ct_provincia or "—"),
                ("CÓDIGO POSTAL", ct_cp or "—"),
                ("PAÍS", _vc(ct_pais, ct_cod_pais or emp_cod_pais)),
            ))
            story.append(_data_val_row(
                ("CÓDIGO CUENTA DE COTIZACIÓN", ct_ccc or emp_ccc or "—"),
                ("ACTIVIDAD ECONÓMICA", _vc(ct_actividad or emp_actividad, ct_cod_act or emp_cod_act)),
            ))
        else:
            story.append(_data_val_row(
                ("MUNICIPIO", _vc(emp_municipio, emp_cod_muni)),
                ("CÓDIGO POSTAL", emp_cp or "—"),
                ("PAÍS", _vc(emp_pais, emp_cod_pais)),
            ))
        story.append(Spacer(1, 1*mm))

        story.append(_sec_header("DATOS DE LA PERSONA TRABAJADORA"))
        story.append(_data_val_row(("D./DÑA.", trab), ("NIF/NIE", nif), ("SEXO", sexo or "—")))
        story.append(_data_val_row(
            ("FECHA NACIMIENTO (dd/mm/aaaa)", fn_nac or "—"),
            ("Nº SEGURIDAD SOCIAL", ss or "—"),
            ("NACIONALIDAD", nacionalidad or "ESPAÑOLA"),
        ))
        story.append(_data_val_row(
            ("NIVEL FORMATIVO", _vc(nivel_formativo, cod_nivel)),
            ("TITULACIÓN", titulacion or "—"),
        ))
        story.append(_data_val_row(("MUNICIPIO DEL DOMICILIO", _vc(municipio_dom, cod_muni_dom)),
                                   ("PROVINCIA", _vc(provincia_dom, cod_prov_dom))))
        story.append(_data_val_row(
            ("CÓDIGO POSTAL", cp_dom or "—"),
            ("PAÍS DOMICILIO", _vc(pais_dom or "ESPAÑA", cod_pais_dom)),
            ("TELÉFONO", tel_trab or "—"),
        ))
        if email_trab:
            story.append(_data_val_row(("CORREO ELECTRÓNICO", email_trab)))
        story.append(Spacer(1, 2*mm))

        # Sección siempre presente (como el modelo oficial), aunque vacía.
        story.append(_sec_header("DATOS DE LA ASISTENCIA LEGAL (EN SU CASO)"))
        story.append(_data_val_row(
            ("TIPO DE REPRESENTACIÓN", asist_tipo if (asist_tipo and asist_tipo != "No procede") else "—"),
            ("ORGANIZACIÓN", asist_org or "—"),
        ))
        story.append(_data_val_row(
            ("D./DÑA.", asist_nombre or "—"),
            ("NIF/NIE", asist_nif or "—"),
            ("CARGO", asist_cargo or "—"),
        ))
        story.append(Spacer(1, 2*mm))

        story.append(_P(
            "Que reúnen los requisitos exigidos para la celebración del presente contrato y, "
            "en su consecuencia, acuerdan formalizarlo con arreglo a las siguientes:",
            st_body
        ))
        story.append(Spacer(1, 1*mm))
        story.append(_sec_header("CLÁUSULAS"))
        story.append(Spacer(1, 1*mm))

        _td_txt = "SÍ" if _distancia_si else "NO"
        story.append(_P(
            f"<b>PRIMERA:</b> El/la trabajador/a prestará sus servicios como <b>{_puesto_txt}</b>, "
            f"incluido/a en el grupo profesional de <b>{_grupo_txt}</b>, para la realización de las "
            f"funciones de <b>{_func_txt}</b>, de acuerdo con el sistema de clasificación profesional "
            f"vigente en la empresa. En el centro de trabajo ubicado en (calle, nº y localidad): "
            f"<b>{_centro_txt}</b>. Modalidad de trabajo a distancia: <b>{_td_txt}</b> "
            f"(Ley 10/2021, de 9 de julio, de trabajo a distancia).",
            st_clause))

        if _es_fijodisc:
            _segunda_txt = (
                f"<b>SEGUNDA:</b> El contrato se concierta para realizar trabajos fijos-discontinuos, "
                f"de acuerdo con el artículo 16 del Estatuto de los Trabajadores. Los/as trabajadores/as "
                f"serán llamados/as en el orden y la forma que se determine en el Convenio Colectivo de "
                f"<b>{_conv_txt}</b> o acuerdo de empresa.")
        elif _es_sustit:
            _segunda_txt = (
                "<b>SEGUNDA:</b> El contrato se concierta para la sustitución de persona trabajadora "
                "con derecho a reserva del puesto de trabajo, de acuerdo con el artículo 15.3 del "
                "Estatuto de los Trabajadores.")
        elif _es_temporal:
            _segunda_txt = (
                "<b>SEGUNDA:</b> El contrato se concierta por circunstancias de la producción de "
                "carácter ocasional e imprevisible, con duración determinada, de acuerdo con el "
                "artículo 15 del Estatuto de los Trabajadores.")
        elif _es_practic:
            _segunda_txt = (
                "<b>SEGUNDA:</b> El contrato se concierta como contrato formativo para la obtención de "
                "la práctica profesional adecuada al nivel de estudios, de acuerdo con el artículo 11.3 "
                "del Estatuto de los Trabajadores.")
        else:
            _segunda_txt = (
                "<b>SEGUNDA:</b> El contrato se concierta por tiempo indefinido, de acuerdo con el "
                "artículo 15 del Estatuto de los Trabajadores.")
        story.append(_P(_segunda_txt, st_clause))

        if _jornada_parcial:
            jornada_txt = (
                f"<b>TERCERA:</b> La jornada de trabajo será <b>a tiempo parcial</b>: <b>{_horas_txt} horas</b> "
                f"a la semana, siendo esta jornada inferior a la de un trabajador a tiempo completo comparable. "
                f"La distribución del tiempo de trabajo será de <b>{_dist_txt}</b>, conforme a lo previsto "
                f"en el convenio colectivo.")
        else:
            jornada_txt = (
                f"<b>TERCERA:</b> La jornada de trabajo será <b>a tiempo completo</b>: <b>{_horas_txt} horas "
                f"semanales</b>, con la distribución horaria de <b>{_dist_txt}</b>, con los descansos "
                f"establecidos legal o convencionalmente.")
        story.append(_P(jornada_txt, st_clause))

        if _es_fijodisc:
            _cuarta_txt = (
                f"<b>CUARTA:</b> El presente contrato es <b>FIJO-DISCONTINUO</b> y de duración "
                f"<b>INDEFINIDA</b>; la relación laboral se inicia en fecha <b>{fecha}</b>, con "
                f"llamamientos sucesivos en el orden y la forma que determine el convenio colectivo. "
                f"Se establece un período de prueba de <b>{_prueba_txt}</b>.")
        elif _es_determinada:
            _fin_txt = (f" y finalizando el <b>{_fecha_fin}</b>" if _fecha_fin
                        else ", extendiéndose mientras subsista la causa que la motiva")
            _cuarta_txt = (
                f"<b>CUARTA:</b> La duración del presente contrato será <b>DETERMINADA</b>, "
                f"iniciándose la relación laboral en fecha <b>{fecha}</b>{_fin_txt}. Se establece un "
                f"período de prueba de <b>{_prueba_txt}</b>.")
        else:
            _cuarta_txt = (
                f"<b>CUARTA:</b> La duración del presente contrato será <b>INDEFINIDA</b>, "
                f"iniciándose la relación laboral en fecha <b>{fecha}</b> y se establece un período de "
                f"prueba de <b>{_prueba_txt}</b>.")
        story.append(_P(_cuarta_txt, st_clause))

        story.append(_P(
            f"<b>QUINTA:</b> El/la trabajador/a percibirá una retribución total de "
            f"<b>{_sal_anual_fmt} euros brutos anuales</b>, que se distribuirán en <b>{num_pagas} pagas</b> "
            f"(importe mensual: <b>{_sal_mensual_fmt}</b>), conforme a los conceptos salariales del "
            f"convenio colectivo y sujetos a las retenciones de IRPF y a las cotizaciones a la "
            f"Seguridad Social legalmente establecidas.",
            st_clause))

        story.append(_P(
            "<b>SEXTA:</b> Complemento de apoyo al empleo para las personas trabajadoras que estén "
            "percibiendo prestaciones por desempleo (disposición adicional 59ª del texto refundido de "
            "la Ley General de la Seguridad Social). La empresa <b>NO</b> tiene autorizado un expediente "
            "de regulación de empleo.",
            st_clause))

        story.append(_P(
            f"<b>SÉPTIMA:</b> La duración de las vacaciones anuales será de <b>{_vac_txt}</b>.",
            st_clause))

        story.append(_P(
            f"<b>OCTAVA:</b> En lo no previsto en este contrato, se estará a la legislación vigente que "
            f"resulte de aplicación y, particularmente, al Estatuto de los Trabajadores (RDL 2/2015) y "
            f"al Convenio Colectivo de <b>{_conv_txt}</b>.",
            st_clause))

        story.append(_P(
            "<b>NOVENA:</b> El presente contrato <b>NO</b> se formaliza bajo la modalidad "
            "de contrato de relevo.",
            st_clause))

        story.append(_P(
            "<b>DÉCIMA:</b> ESTE CONTRATO PODRÁ SER COFINANCIADO POR EL FONDO SOCIAL EUROPEO.",
            st_clause))

        story.append(_P(
            "<b>UNDÉCIMA:</b> El contenido del presente contrato se comunicará al Servicio Público de "
            "Empleo en el plazo de los 10 días siguientes a su concertación (art. 16.1 de la Ley de Empleo).",
            st_clause))

        story.append(_P(
            "<b>DUODÉCIMA:</b> PROTECCIÓN DE DATOS. Los datos consignados en el presente modelo tendrán "
            "la protección derivada del Reglamento (UE) 2016/679 del Parlamento Europeo y del Consejo, "
            "de 27 de abril de 2016, y de la Ley Orgánica 3/2018, de 5 de diciembre (LOPDGDD).",
            st_clause))
        story.append(Spacer(1, 2*mm))

        story.append(_sec_header("TIPO DE CONTRATO — CÓDIGO"))
        if _es_fijodisc:
            _cod_num = "300"
            _mk_completo, _mk_parcial, _mk_fijo = "☐", "☐", "☑"
        elif _jornada_parcial:
            _cod_num = "200"
            _mk_completo, _mk_parcial, _mk_fijo = "☐", "☑", "☐"
        else:
            _cod_num = "100"
            _mk_completo, _mk_parcial, _mk_fijo = "☑", "☐", "☐"
        cod_data = [[
            Paragraph(
                f"{_mk_completo}  TIEMPO COMPLETO    "
                f"{_mk_parcial}  TIEMPO PARCIAL    "
                f"{_mk_fijo}  FIJO-DISCONTINUO",
                st_body
            ),
            Paragraph(
                _cod_num,
                _st("cod", fontName=_FB, fontSize=14, textColor=AZUL,
                    leading=16, alignment=TA_CENTER)
            ),
        ]]
        story.append(Table(cod_data, colWidths=[usable_w*0.75, usable_w*0.25],
            style=TableStyle([
                ("BOX", (0,0),(-1,-1), 0.6, BORDE_OSC),
                ("INNERGRID",(0,0),(-1,-1), 0.4, BORDE),
                ("TOPPADDING",(0,0),(-1,-1), 5),
                ("BOTTOMPADDING",(0,0),(-1,-1), 5),
                ("LEFTPADDING",(0,0),(-1,-1), 8),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ])))

        if clausulas_adicionales:
            story.append(Spacer(1, 3*mm))
            story.append(_sec_header("CLÁUSULAS ADICIONALES — SEGÚN ANEXO"))
            story.append(Spacer(1, 1*mm))
            _cla_map = {
                "Prorrateo de pagas extraordinarias":
                    "Empresa y trabajador/a acuerdan el prorrateo de las gratificaciones "
                    "extraordinarias establecidas por el convenio colectivo, de forma que "
                    "el/la trabajador/a percibirá mensualmente el importe correspondiente "
                    "a las pagas extraordinarias devengadas.",
                "Obligaciones de no competencia desleal (arts. 4.1 y 21.1 ET)":
                    "El/La trabajador/a deberá abstenerse de inducir a trabajadores, "
                    "proveedores o clientes a infringir deberes contractuales, de conformidad "
                    "con los arts. 4.1 y 21.1 ET y los arts. 4.1 y 14 de la Ley de Competencia Desleal.",
                "Uso restringido de Internet y correo corporativo":
                    "El acceso a Internet y el correo electrónico corporativo tienen carácter "
                    "estrictamente laboral. La empresa informa de la existencia de mecanismos "
                    "de control del uso de los medios informáticos de la empresa.",
                "Protección de datos personales (LOPDGDD 3/2018)":
                    "Los datos personales serán tratados conforme a la LOPDGDD 3/2018 y el "
                    "RGPD (UE) 2016/679. Podrán comunicarse a terceros exclusivamente cuando "
                    "sea necesario para el desarrollo de la relación laboral.",
                "Compensación de horas extra con descanso":
                    "El exceso de horas laborables respecto al calendario y el convenio "
                    "colectivo se compensará de común acuerdo con horas de descanso equivalentes.",
                "Interrupción del período de prueba por IT/nacimiento":
                    "Las situaciones de IT, nacimiento, adopción, guarda, acogimiento, riesgo "
                    "durante el embarazo o la lactancia y violencia de género interrumpirán "
                    "el cómputo del período de prueba.",
                "Vacaciones en días laborables":
                    "Las vacaciones anuales retribuidas se disfrutarán en días laborables, "
                    "respetando en todo caso la duración total establecida en convenio.",
                "Obligación de comunicar baja/alta médica de forma inmediata":
                    "En casos de baja/alta médica, el/la trabajador/a informará a la empresa "
                    "de forma inmediata. El parte médico se remite por vía telemática.",
            }
            numerales = ["PRIMERA","SEGUNDA","TERCERA","CUARTA","QUINTA",
                         "SEXTA","SÉPTIMA","OCTAVA","NOVENA","DÉCIMA"]
            for i, cla_txt in enumerate(clausulas_adicionales, 1):
                num = numerales[min(i-1, 9)]
                cla_body = _cla_map.get(cla_txt, cla_txt)
                story.append(_P(f"<b>{num}.</b> {cla_body}", st_clause))

        # ── Anexo específico según la modalidad contractual ──
        _anexos = []
        if _jornada_parcial:
            _anexos.append((
                "ANEXO — PACTO DE HORAS COMPLEMENTARIAS",
                "El/la trabajador/a a tiempo parcial podrá realizar horas complementarias hasta "
                "un máximo del 30% de las horas ordinarias (ampliable por convenio colectivo de "
                "ámbito sectorial hasta el 60%), con un preaviso mínimo de 3 días, conforme al "
                "artículo 12.5 del Estatuto de los Trabajadores. Se retribuirán como ordinarias y "
                "computarán a efectos de cotización a la Seguridad Social."))
        if _es_fijodisc:
            _anexos.append((
                "ANEXO — TRABAJO FIJO-DISCONTINUO",
                "El llamamiento se realizará por escrito, en el orden y la forma que determine el "
                "convenio colectivo, con antelación suficiente. La falta de llamamiento equivaldrá a "
                "un despido a efectos legales. Los periodos de inactividad no interrumpen el cómputo "
                "de la antigüedad (art. 16 del Estatuto de los Trabajadores)."))
        if _es_temporal:
            _anexos.append((
                "ANEXO — CONTRATO DE DURACIÓN DETERMINADA",
                "El contrato se extinguirá al finalizar la causa que lo motiva o, en su caso, en la "
                "fecha pactada. A su término, el/la trabajador/a tendrá derecho a la indemnización "
                "legalmente establecida (art. 49 del Estatuto de los Trabajadores)."))
        if _es_practic:
            _anexos.append((
                "ANEXO FORMATIVO",
                "La empresa designa un/a tutor/a responsable del seguimiento del plan formativo "
                "individual. La actividad se ajustará al nivel de estudios de la persona trabajadora "
                "(art. 11.3 del Estatuto de los Trabajadores), con una duración mínima de 6 meses y "
                "máxima de 1 año."))
        if _anexos:
            story.append(Spacer(1, 2*mm))
            story.append(_sec_header("ANEXO ESPECÍFICO DE LA MODALIDAD"))
            story.append(Spacer(1, 1*mm))
            for _ax_t, _ax_b in _anexos:
                story.append(_P(f"<b>{_ax_t}.</b> {_ax_b}", st_clause))



def render_contrato(ctx):
    ejecutar(_impl, ctx)
