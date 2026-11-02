"""
Vista móvil de plugins instalados (Fase 9). Proyecta `sdk.listar_instalados` a un subconjunto de
campos seguro para el móvil (sin `ruta` de servidor ni el `manifest` JSON crudo — higiene, no porque
haya nada sensible: los secretos de conectores viven aparte, cifrados, fuera de este módulo).
"""


def instalados(id_empresa) -> list[dict]:
    from src import sdk
    filas = sdk.listar_instalados(id_empresa)
    return [
        {
            "clave": f.get("clave"),
            "nombre": f.get("nombre"),
            "version": f.get("version"),
            "autor": f.get("autor"),
            "estado": f.get("estado"),
            "actualizado": str(f.get("actualizado") or ""),
        }
        for f in filas
    ]
