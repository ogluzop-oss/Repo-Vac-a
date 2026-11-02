"""
Migración 0273 — Cimientos del perfil fiscal: catálogo de epígrafes IAE, asignación por empresa y
deducciones sectoriales (Fase A de "Smart Accounting: epígrafe IAE, régimen IRPF..."). Mismo idioma
que `fiscal_is_reglas` (migr. 0237): catálogo editable en tabla, nunca un fichero/JSON a mano.

`fiscal_iae_epigrafes`: catálogo BUSCABLE, no el listado oficial completo (miles de epígrafes) — un
subconjunto representativo por sección (1ª Empresarial / 2ª Profesional / 3ª Artística), con alta
manual de un epígrafe no listado siempre disponible desde la propia pantalla. `regimen_irpf_defecto`
distingue 'modulos' (Estimación Objetiva) de 'estimacion_directa_simplificada'/'estimacion_directa_
normal': tras la Ley 26/2014, módulos solo aplica a un catálogo tasado y cada vez más reducido de
actividades (Orden HAC anual) — la mayoría de epígrafes de este catálogo usan la Directa Simplificada
por defecto a propósito. `requiere_modelo_130`: en régimen de módulos el pago fraccionado de un
autónomo se declara en el Modelo 131, NO en el 130 — por eso las filas con régimen 'modulos' llevan
`requiere_modelo_130=0` (lo exigible ahí es el 131, fuera del alcance de esta fase). `requiere_modelo_
303=0` SOLO en las actividades genuinamente exentas de IVA del art. 20 LIVA (sanidad, enseñanza
reglada, servicios financieros, seguros) — el resto de epígrafes, aunque tributen a tipo reducido
(p. ej. alimentación), siguen sujetos y no exentos, así que llevan 1.

`fiscal_empresa_epigrafe`: la asignación real por empresa. Cardinalidad MÚLTIPLE a propósito (no
"una activa a la vez"): una empresa/autónomo puede estar dado de alta en VARIOS epígrafes IAE
simultáneos (p. ej. quien compagina comercio al por menor y hostelería) — es una situación legal
habitual, no una excepción. `activo`/`fecha_baja` permiten desactivar una asignación sin borrar el
historial (mismo criterio "soft delete" que el resto de catálogos de esta app).

`fiscal_deducciones_sectoriales`: reglas de deducción por epígrafe (`id_epigrafe` NULL = general,
aplica a cualquier actividad) resueltas por especificidad (epígrafe propio > general), mismo patrón
que `fiscal_is_reglas.resolver()`. Semilla con cifras REALES vigentes de Hacienda (dietas de
manutención, art. 9 RIRPF) y la deducción de suministros del hogar (art. 11 RIRPF, redacción de la
Ley 6/2017 de Reformas Urgentes del Trabajo Autónomo) — ver citas legales en `condiciones` de cada
fila sembrada.
"""

import datetime as _dt

VERSION = "0273"
DESCRIPCION = "Cimientos perfil fiscal: epígrafes IAE, asignación por empresa, deducciones sectoriales"
REVERSIBLE = True
REQUIERE_BACKUP = False

_DIRECTA_SIMPLIFICADA = "estimacion_directa_simplificada"
_DIRECTA_NORMAL = "estimacion_directa_normal"
_MODULOS = "modulos"

# (seccion, codigo, descripcion, regimen_irpf_defecto, requiere_130, requiere_303, requiere_111_si_personal)
#
# requiere_modelo_130 = 0 cuando el régimen por defecto es 'modulos' (esas actividades declaran el
# pago fraccionado en el Modelo 131, no en el 130 — fuera de alcance de esta fase).
# requiere_modelo_303 = 0 SOLO en las 4 actividades realmente exentas de IVA por el art. 20 LIVA
# (sanidad, enseñanza reglada, servicios financieros, seguros).
# requiere_modelo_111_si_personal = 1 en todas: el Modelo 111 depende de si la empresa tiene personal
# o retiene a profesionales, no del epígrafe — el flag es informativo/condicional, no una restricción.
_EPIGRAFES = (
    # ── Sección 1ª Empresarial — comercio al por menor de alimentación (Grupos 641-647): el núcleo
    # histórico de Estimación Objetiva/módulos, siguen vigentes tras la reforma de 2015 (Orden HAC
    # anual, Anexo II). Sujetos a IVA (tipos reducidos en alimentación, pero NO exentos).
    ("empresarial", "641", "Comercio al por menor de frutas, verduras, hortalizas y frutos secos",
     _MODULOS, 0, 1, 1),
    ("empresarial", "642.1", "Comercio al por menor de carnes y despojos; productos y derivados cárnicos",
     _MODULOS, 0, 1, 1),
    ("empresarial", "644.1", "Comercio al por menor de pan, pastelería, confitería y similares",
     _MODULOS, 0, 1, 1),
    ("empresarial", "647.1", "Comercio al por menor de productos alimenticios y bebidas en general "
     "(pequeño comercio de barrio)", _MODULOS, 0, 1, 1),
    # Comercio NO alimentario de cierto volumen: quedó FUERA de módulos tras la reforma de 2015 —
    # directa simplificada por defecto (no se fuerza módulos donde ya no aplica).
    ("empresarial", "653.1", "Comercio al por menor de electrodomésticos, muebles de cocina y de baño",
     _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    ("empresarial", "654.2", "Comercio al por menor de accesorios y piezas de recambio para vehículos "
     "terrestres", _MODULOS, 0, 1, 1),
    ("empresarial", "663.1", "Comercio al por menor fuera de establecimiento (mercadillos/ambulante) "
     "de productos alimenticios", _MODULOS, 0, 1, 1),
    # Hostelería/restauración: restaurantes de hasta dos tenedores, cafeterías y bares siguen en
    # módulos; los de más categoría (lujo) quedaron excluidos — no se incluyen aquí a propósito.
    ("empresarial", "671.4", "Restaurantes de dos tenedores", _MODULOS, 0, 1, 1),
    ("empresarial", "672.1", "Cafeterías", _MODULOS, 0, 1, 1),
    ("empresarial", "673.2", "Otros cafés y bares", _MODULOS, 0, 1, 1),
    ("empresarial", "681", "Servicio de hospedaje en hoteles y moteles de una y dos estrellas",
     _MODULOS, 0, 1, 1),
    # Construcción/reformas: SOLO albañilería y pequeños trabajos de reforma quedaron en módulos tras
    # 2015 — el resto de oficios de construcción (carpintería, cerrajería, instalaciones) salió del
    # régimen, por eso NO se marcan como módulos aquí (directa simplificada).
    ("empresarial", "501.3", "Albañilería y pequeños trabajos de construcción en general",
     _MODULOS, 0, 1, 1),
    ("empresarial", "505.7", "Carpintería y cerrajería (instalación/reparación)",
     _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    ("empresarial", "833.2", "Promoción inmobiliaria de edificaciones",
     _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    # Transporte: mercancías/mudanzas y autotaxi siguen en el catálogo de módulos.
    ("empresarial", "721.1", "Transporte de mercancías por carretera y servicios de mudanzas",
     _MODULOS, 0, 1, 1),
    ("empresarial", "722", "Transporte de viajeros por carretera: autotaxis", _MODULOS, 0, 1, 1),
    ("empresarial", "751.5", "Engrase y lavado de vehículos", _MODULOS, 0, 1, 1),
    # Peluquería/estética/tintorería: catálogo clásico de módulos, sigue vigente.
    ("empresarial", "972.1", "Peluquerías", _MODULOS, 0, 1, 1),
    ("empresarial", "972.2", "Salones e institutos de belleza", _MODULOS, 0, 1, 1),
    ("empresarial", "951.1", "Tinte, limpieza en seco, lavado y planchado de ropas",
     _MODULOS, 0, 1, 1),
    # Agrícola/ganadero: régimen de Estimación Objetiva Agraria (variante propia, aquí representada
    # con la misma etiqueta 'modulos' del enum — no exenta de IVA salvo régimen especial REAGP aparte).
    ("empresarial", "911", "Explotación agrícola y ganadera (cultivo y cría en general)",
     _MODULOS, 0, 1, 1),
    # Actividades genuinamente EXENTAS de IVA (art. 20.Uno LIVA): sanidad, enseñanza reglada,
    # servicios financieros y seguros. requiere_modelo_303 = 0 exclusivamente aquí.
    ("empresarial", "941.1", "Hospitales, clínicas y sanatorios (asistencia sanitaria)",
     _DIRECTA_SIMPLIFICADA, 1, 0, 1),
    ("empresarial", "931", "Enseñanza reglada (educación infantil, primaria, secundaria y superior)",
     _DIRECTA_SIMPLIFICADA, 1, 0, 1),
    ("empresarial", "812", "Servicios financieros (bancos y otras entidades de crédito)",
     _DIRECTA_NORMAL, 0, 0, 1),
    ("empresarial", "813", "Seguros (entidades aseguradoras)", _DIRECTA_NORMAL, 0, 0, 1),
    # ── Sección 2ª Profesional: NUNCA módulos (el régimen de Estimación Objetiva es exclusivo de
    # Sección 1ª Empresarial) — siempre Estimación Directa. Sujetos a retención en factura (IRPF)
    # cuando facturan a otros profesionales/empresas, pero eso no exime del 303 (no es de las 4
    # exenciones del art. 20 LIVA).
    ("profesional", "511", "Abogados", _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    ("profesional", "513", "Economistas y Titulados Mercantiles (asesoría fiscal-contable)",
     _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    ("profesional", "611", "Ingenieros", _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    ("profesional", "621", "Médicos (ejercicio libre de la profesión)",
     _DIRECTA_SIMPLIFICADA, 1, 0, 1),
    ("profesional", "725", "Agentes comerciales", _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    ("profesional", "751", "Programadores y analistas de informática (consultoría/desarrollo TI)",
     _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    # ── Sección 3ª Artística: nunca módulos, siempre Directa. Sujetas a IVA (no son de las
    # exenciones del art. 20 LIVA) y a retención en factura si facturan a un pagador obligado a retener.
    ("artistica", "03", "Pintores, escultores, ceramistas, artesanos y grabadores",
     _DIRECTA_SIMPLIFICADA, 1, 1, 1),
    ("artistica", "05", "Músicos y cantantes", _DIRECTA_SIMPLIFICADA, 1, 1, 1),
)

# (concepto, id_epigrafe_codigo|None, porcentaje, importe_fijo, condiciones, prioridad)
#
# Cifras REALES vigentes (Hacienda, art. 9 RIRPF — dietas exceptuadas de gravamen; art. 11 RIRPF —
# gastos de suministros del hogar del trabajador autónomo). Las reglas ligadas a un epígrafe concreto
# (`id_epigrafe` no NULL) son MÁS ESPECÍFICAS que la regla general del mismo concepto y ganan en
# `resolver_deducciones()` (mismo criterio de especificidad que `fiscal_is_reglas.resolver()`).
_DEDUCCIONES = (
    ("suministros_hogar", None, 30.00, None,
     "30% de la proporción de metros cuadrados de la vivienda habitual afectos a la actividad "
     "económica sobre el total de la vivienda, aplicado sobre los gastos de suministros (agua, gas, "
     "electricidad, telefonía e internet). Requiere trabajo habitual desde el domicilio declarado y "
     "declarar el porcentaje de la vivienda afecto. Base legal: art. 11 del Reglamento del IRPF "
     "(RD 439/2007), en la redacción dada por la Ley 6/2017, de 24 de octubre, de Reformas Urgentes "
     "del Trabajo Autónomo.", 0),
    ("dietas_manutencion_nacional", None, None, 26.67,
     "26,67 €/día por gastos de manutención del propio contribuyente en el desarrollo de la "
     "actividad, sin pernoctar en territorio español, siempre que se produzcan en establecimientos "
     "de restauración y hostelería, se abonen con medios electrónicos y se conserve el justificante. "
     "Base legal: art. 9 del Reglamento del IRPF (RD 439/2007), por remisión a los límites "
     "reglamentarios de dietas exceptuadas de gravamen.", 0),
    ("dietas_manutencion_nacional_pernocta", None, None, 53.34,
     "53,34 €/día si el desplazamiento por motivos de la actividad exige pernoctar en territorio "
     "español. Mismos requisitos de medio de pago electrónico y conservación del justificante que "
     "sin pernocta. Base legal: art. 9 del Reglamento del IRPF (RD 439/2007).", 0),
    ("dietas_manutencion_extranjero", None, None, 48.08,
     "48,08 €/día por gastos de manutención en el extranjero, sin pernoctar. Base legal: art. 9 del "
     "Reglamento del IRPF (RD 439/2007).", 0),
    ("dietas_manutencion_extranjero_pernocta", None, None, 91.35,
     "91,35 €/día por gastos de manutención en el extranjero, pernoctando. Base legal: art. 9 del "
     "Reglamento del IRPF (RD 439/2007).", 0),
    # Deducción sectorial del vehículo: el criterio general de Hacienda exige "afectación exclusiva"
    # del vehículo a la actividad para deducir el 100% (en la práctica, inviable de probar salvo
    # excepción). La propia normativa (art. 22 Reglamento IVA/criterio DGT) reconoce una lista TASADA
    # de actividades en las que el vehículo se presume afecto: transporte de mercancías/viajeros,
    # autoescuelas, agentes comerciales (con matiz de "uso mixto" del 50%), vigilancia... — de ahí
    # las dos filas ESPECÍFICAS de epígrafe (más específicas que cualquier regla general) que siguen.
    ("vehiculo_uso_actividad", "721.1", 100.00, None,
     "100% de los gastos del vehículo (amortización, combustible, seguro, mantenimiento) cuando la "
     "actividad consiste en el transporte de mercancías por carretera: excepción tasada al criterio "
     "general de 'afectación exclusiva' (art. 22 del Reglamento del IVA, RD 1624/1992, y criterio "
     "reiterado de la DGT en consulta vinculante para vehículos afectos a actividades de transporte).",
     10),
    ("vehiculo_uso_actividad", "722", 100.00, None,
     "100% de los gastos del vehículo cuando la actividad es el transporte de viajeros en autotaxi: "
     "misma excepción tasada del art. 22 del Reglamento del IVA (RD 1624/1992) para vehículos afectos "
     "a actividades de transporte.", 10),
    ("vehiculo_uso_actividad", "725", 50.00, None,
     "50% de los gastos del vehículo para agentes comerciales que lo usan de forma mixta (particular "
     "y profesional) en su actividad de representación, que exige desplazamiento habitual: criterio "
     "administrativo asentado en consultas de la DGT para vehículos mixtos de agentes comerciales, "
     "distinto del 100% de las actividades de transporte tasadas en el art. 22 del Reglamento del IVA.",
     10),
)


def _existe_tabla(cur, tabla) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s", (tabla,))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _existe_tabla(cur, "fiscal_iae_epigrafes"):
        cur.execute("""
            CREATE TABLE fiscal_iae_epigrafes (
                id                              INT AUTO_INCREMENT PRIMARY KEY,
                seccion                         VARCHAR(20)  NOT NULL,
                codigo                          VARCHAR(20)  NOT NULL,
                descripcion                     VARCHAR(255) NOT NULL,
                regimen_irpf_defecto            VARCHAR(40)  NOT NULL DEFAULT 'estimacion_directa_simplificada',
                requiere_modelo_130             TINYINT(1)   NOT NULL DEFAULT 1,
                requiere_modelo_303             TINYINT(1)   NOT NULL DEFAULT 1,
                requiere_modelo_111_si_personal TINYINT(1)   NOT NULL DEFAULT 1,
                activo                          TINYINT(1)   NOT NULL DEFAULT 1,
                creado                          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_fiscaliae_codigo (codigo),
                INDEX idx_fiscaliae_seccion (seccion)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

    if not _existe_tabla(cur, "fiscal_empresa_epigrafe"):
        cur.execute("""
            CREATE TABLE fiscal_empresa_epigrafe (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                id_empresa   VARCHAR(36) NOT NULL,
                id_epigrafe  INT         NOT NULL,
                fecha_alta   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_baja   DATETIME    DEFAULT NULL,
                activo       TINYINT(1)  NOT NULL DEFAULT 1,
                INDEX idx_fiscalempep_emp (id_empresa, activo),
                INDEX idx_fiscalempep_epig (id_epigrafe)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

    if not _existe_tabla(cur, "fiscal_deducciones_sectoriales"):
        cur.execute("""
            CREATE TABLE fiscal_deducciones_sectoriales (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                id_epigrafe  INT           DEFAULT NULL,
                concepto     VARCHAR(60)   NOT NULL,
                porcentaje   DECIMAL(5,2)  DEFAULT NULL,
                importe_fijo DECIMAL(10,2) DEFAULT NULL,
                condiciones  TEXT          DEFAULT NULL,
                activo       TINYINT(1)    NOT NULL DEFAULT 1,
                prioridad    INT           NOT NULL DEFAULT 0,
                creado       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_fiscaldedsec_epig (id_epigrafe),
                INDEX idx_fiscaldedsec_concepto (concepto)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

    # Semilla del catálogo de epígrafes — INSERT IGNORE sobre la UNIQUE(codigo): idempotente, no
    # duplica en reaplicaciones ni pisa ediciones manuales posteriores del usuario.
    ahora = _dt.datetime.now()
    for seccion, codigo, descripcion, regimen, req130, req303, req111 in _EPIGRAFES:
        cur.execute(
            "INSERT IGNORE INTO fiscal_iae_epigrafes "
            "(seccion, codigo, descripcion, regimen_irpf_defecto, requiere_modelo_130, "
            "requiere_modelo_303, requiere_modelo_111_si_personal, activo, creado) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s)",
            (seccion, codigo, descripcion, regimen, req130, req303, req111, ahora))

    # Mapa código -> id para las deducciones sectoriales ligadas a un epígrafe concreto.
    cur.execute("SELECT id, codigo FROM fiscal_iae_epigrafes")
    filas = cur.fetchall()
    if filas and isinstance(filas[0], dict):
        codigo_a_id = {f["codigo"]: f["id"] for f in filas}
    else:
        codigo_a_id = {codigo: id_ for id_, codigo in filas}

    # Semilla de deducciones sectoriales — evita duplicar si ya existe una fila idéntica
    # (mismo concepto + mismo id_epigrafe, NULL incluido).
    for concepto, codigo_epig, porcentaje, importe_fijo, condiciones, prioridad in _DEDUCCIONES:
        id_epigrafe = codigo_a_id.get(codigo_epig) if codigo_epig else None
        if codigo_epig and id_epigrafe is None:
            continue  # epígrafe no encontrado (no debería ocurrir): no se inventa la fila
        if id_epigrafe is None:
            cur.execute(
                "SELECT COUNT(*) FROM fiscal_deducciones_sectoriales "
                "WHERE concepto=%s AND id_epigrafe IS NULL", (concepto,))
        else:
            cur.execute(
                "SELECT COUNT(*) FROM fiscal_deducciones_sectoriales "
                "WHERE concepto=%s AND id_epigrafe=%s", (concepto, id_epigrafe))
        r = cur.fetchone()
        existe = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0
        if existe:
            continue
        cur.execute(
            "INSERT INTO fiscal_deducciones_sectoriales "
            "(id_epigrafe, concepto, porcentaje, importe_fijo, condiciones, activo, prioridad, creado) "
            "VALUES (%s,%s,%s,%s,%s,1,%s,%s)",
            (id_epigrafe, concepto, porcentaje, importe_fijo, condiciones, prioridad, ahora))


def revertir(cur):
    # Reversible SOLO de esta migración: dropea las 3 tablas completas (aditivas, sin dependientes
    # aún — Fase A es la primera en tocarlas).
    for tabla in ("fiscal_deducciones_sectoriales", "fiscal_empresa_epigrafe", "fiscal_iae_epigrafes"):
        cur.execute(f"DROP TABLE IF EXISTS {tabla}")
