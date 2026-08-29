"""
Migración 0225 — Retira el rol GERENTE del sistema; ADMINISTRADOR pasa a cubrir sus
responsabilidades (decisión de producto: un solo rol intermedio, no dos). Solo datos.

GERENTE ya no aparece en el catálogo RBAC (`services.seguridad.catalogo.ROLES_SISTEMA`) ni en
ningún gate de la aplicación — en todos los sitios donde antes se comprobaba
`perfil in (..., "GERENTE", ...)`, ADMINISTRADOR (comodín "*") ya cubría estrictamente el mismo
conjunto de permisos o más, así que no hay ninguna capacidad que se pierda al retirarlo. Esta
migración limpia las filas EXISTENTES que aún contengan el valor literal 'GERENTE', para que
ninguna comprobación de rol quede huérfana contra un valor que ya no existe en el catálogo
(p. ej. un paso de workflow con `rol_requerido='GERENTE'` dejaría de poder aprobarlo NADIE).
"""

VERSION = "0225"
DESCRIPCION = "Retirar el rol GERENTE (ADMINISTRADOR asume sus responsabilidades)"
REVERSIBLE = False   # fusiona GERENTE en ADMINISTRADOR; no se puede reconstruir la distinción original
REQUIERE_BACKUP = True


def _tabla_existe(cur, tabla):
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s", (tabla,))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n) > 0


def _columna_existe(cur, tabla, columna):
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n) > 0


def _fila_a_tupla(fila, claves):
    if isinstance(fila, dict):
        return tuple(fila.get(k) for k in claves)
    return tuple(fila)


def aplicar(cur):
    # 1) Perfil legado del usuario (motor principal de casi todos los gates por rol).
    if _tabla_existe(cur, "usuarios") and _columna_existe(cur, "usuarios", "perfil"):
        cur.execute("UPDATE usuarios SET perfil='ADMINISTRADOR' WHERE perfil='GERENTE'")

    # 2) Vínculo multiempresa (rol por empresa, texto libre — services.saas.multiempresa).
    if _tabla_existe(cur, "usuarios_empresas") and _columna_existe(cur, "usuarios_empresas", "rol"):
        cur.execute("UPDATE usuarios_empresas SET rol='ADMINISTRADOR' WHERE rol='GERENTE'")

    # 3) Workflow: plantillas ya sembradas (definición del paso) y tareas ya creadas (instancias
    #    en curso) que quedarían sin nadie que pueda aprobarlas si no se corrige.
    if _tabla_existe(cur, "wf_pasos") and _columna_existe(cur, "wf_pasos", "rol_requerido"):
        cur.execute("UPDATE wf_pasos SET rol_requerido='ADMINISTRADOR' WHERE rol_requerido='GERENTE'")
    if _tabla_existe(cur, "wf_tareas") and _columna_existe(cur, "wf_tareas", "asignado_rol"):
        cur.execute("UPDATE wf_tareas SET asignado_rol='ADMINISTRADOR' WHERE asignado_rol='GERENTE'")

    # 4) Política MFA por empresa: columna de texto libre, códigos separados por coma.
    if _tabla_existe(cur, "mfa_politica") and _columna_existe(cur, "mfa_politica", "roles_obligatorios"):
        cur.execute(
            "UPDATE mfa_politica SET roles_obligatorios=REPLACE(roles_obligatorios,'GERENTE','ADMINISTRADOR') "
            "WHERE roles_obligatorios LIKE '%GERENTE%'")

    # 5) Notificaciones ya emitidas dirigidas al rol antiguo.
    if _tabla_existe(cur, "notificaciones_destinatarios") and _columna_existe(
            cur, "notificaciones_destinatarios", "rol_destino"):
        cur.execute("UPDATE notificaciones_destinatarios SET rol_destino='ADMINISTRADOR' "
                    "WHERE rol_destino='GERENTE'")

    # 6) RBAC granular (roles/usuarios_roles/roles_permisos, sincronizado por empresa desde el
    #    catálogo): el rol GERENTE, si llegó a sincronizarse, se retira por completo. Los usuarios
    #    que lo tuvieran asignado pasan a tener el rol ADMINISTRADOR de esa misma empresa (que ya
    #    existe siempre — SUPERADMIN/ADMINISTRADOR se siembran primero) antes de borrar el vínculo.
    if (_tabla_existe(cur, "roles") and _tabla_existe(cur, "usuarios_roles")
            and _tabla_existe(cur, "roles_permisos")):
        cur.execute("SELECT id, id_empresa FROM roles WHERE codigo='GERENTE'")
        filas_ger = [_fila_a_tupla(f, ("id", "id_empresa")) for f in cur.fetchall()]
        for id_rol_ger, id_empresa in filas_ger:
            cur.execute("SELECT id FROM roles WHERE codigo='ADMINISTRADOR' AND id_empresa=%s",
                        (id_empresa,))
            r_admin = cur.fetchone()
            id_rol_admin = _fila_a_tupla(r_admin, ("id",))[0] if r_admin else None
            if id_rol_admin:
                cur.execute("SELECT id_usuario, ambito_tipo, ambito_id FROM usuarios_roles "
                            "WHERE id_rol=%s", (id_rol_ger,))
                for u in [_fila_a_tupla(f, ("id_usuario", "ambito_tipo", "ambito_id"))
                          for f in cur.fetchall()]:
                    uid, amb_t, amb_i = u
                    cur.execute(
                        "INSERT IGNORE INTO usuarios_roles (id_empresa, id_usuario, id_rol, "
                        "ambito_tipo, ambito_id) VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, uid, id_rol_admin, amb_t, amb_i))
            cur.execute("DELETE FROM usuarios_roles WHERE id_rol=%s", (id_rol_ger,))
            cur.execute("DELETE FROM roles_permisos WHERE id_rol=%s", (id_rol_ger,))
        cur.execute("DELETE FROM roles WHERE codigo='GERENTE'")


def revertir(cur):
    pass
