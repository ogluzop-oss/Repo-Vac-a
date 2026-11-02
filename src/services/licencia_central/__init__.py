"""
Cliente de licenciamiento central (proyecto "servidor central + panel del fundador").

Ver plan en curso. `identidad.obtener_installation_id()` es el identificador real, único por
instalación, que el futuro servidor central usará para distinguir clientes — DISTINTO de
`id_empresa` (que sigue siendo el UUID compartido `EMPRESA_DEFAULT_ID` para el aislamiento de
datos LOCAL entre módulos; no se toca).
"""
