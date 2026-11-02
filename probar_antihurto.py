"""
Script de PRUEBA para simular una alarma antihurto sin hardware EAS real, y comprobar que llega el
push al móvil. Rellena las dos variables de abajo y ejecútalo con el móvil ya con sesión iniciada en
la app (para que el token de ese dispositivo ya esté registrado).
"""

# 1) El nombre de usuario CON EL QUE INICIASTE SESIÓN en el móvil (tal cual aparece en Smart Manager).
NOMBRE_USUARIO = "ADMIN"

# 2) Cualquier código de artículo real de tu catálogo (para la prueba, da igual si tiene foto o no).
CODIGO_ARTICULO = "ART001"


def main():
    from src.db.conexion import obtener_conexion
    from src.services.rfid import antihurto

    with obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT id, id_empresa FROM usuarios WHERE nombre=%s", (NOMBRE_USUARIO,))
        fila = cur.fetchone()

    if not fila:
        print(f"No encuentro ningún usuario llamado '{NOMBRE_USUARIO}'. Revisa que el nombre "
              "sea exactamente el mismo con el que iniciaste sesión en el móvil.")
        return

    id_usuario, id_empresa = (fila["id"], fila["id_empresa"]) if isinstance(fila, dict) else fila

    r = antihurto.alarma_salida_no_pagada(
        ean=CODIGO_ARTICULO,
        id_empresa=id_empresa,
        guardias=[str(id_usuario)],   # se avisa a este usuario aunque no esté "registrado como guardia"
        verificar_pago=False,          # ignora si el artículo consta como vendido (esto es una prueba)
    )
    print(r)

    if r.get("notificados", 0) >= 1:
        print("\nAlarma simulada y enviada. Revisa el móvil (con la app abierta o en segundo plano).")
    elif r.get("motivo") == "articulo_no_identificado":
        print(f"\nNo existe ningún artículo con código '{CODIGO_ARTICULO}'. Prueba con otro código real.")
    else:
        print("\nNo se ha enviado ningún push. Motivo:", r.get("motivo") or "desconocido — "
              "revisa que el usuario haya iniciado sesión en el móvil al menos una vez "
              "(así se registra su token) y que la empresa tenga plan Plus/Pro (o ninguna licencia "
              "asignada, que por defecto da acceso completo).")


if __name__ == "__main__":
    main()
