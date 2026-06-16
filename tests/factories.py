"""
Fábrica de datos de prueba con LIMPIEZA automática.

Cada método inserta una fila (o crea una entidad vía servicio) y registra cómo
borrarla; `limpiar()` deshace todo en orden inverso al terminar el test. Opera
SIEMPRE sobre la base de datos de pruebas (`*_test`, aislada), por lo que es
seguro usar incluso la empresa por defecto.
"""

import uuid


class Fabrica:
    def __init__(self, conexion_mod):
        self.cx = conexion_mod
        self.EMP_DEFECTO = conexion_mod.EMPRESA_DEFAULT_ID
        self._deshacer = []          # lista de callables (LIFO)

    # ── infraestructura ──────────────────────────────────────────────────────
    def _exec(self, sql, params=()):
        with self.cx.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid

    def _borrar(self, tabla, col, val):
        self._deshacer.append(lambda: self._exec(f"DELETE FROM {tabla} WHERE {col}=%s", (val,)))

    def al_limpiar(self, fn):
        """Registra una limpieza personalizada (callable sin args)."""
        self._deshacer.append(fn)

    def limpiar(self):
        for fn in reversed(self._deshacer):
            try:
                fn()
            except Exception:
                pass
        self._deshacer.clear()

    # ── entidades ────────────────────────────────────────────────────────────
    def empresa(self, nombre="EMPRESA TEST"):
        eid = str(uuid.uuid4())
        cod = "T-" + eid[:8]
        self._exec("INSERT INTO empresas (id_empresa, codigo_empresa, nombre_empresa) "
                   "VALUES (%s,%s,%s)", (eid, cod, nombre))
        self._borrar("empresas", "id_empresa", eid)
        return eid

    def articulo(self, codigo=None, id_empresa=None, nombre="Articulo Test",
                 precio=1.0, stock_total=0, stock_tienda=0):
        codigo = codigo or ("T" + uuid.uuid4().hex[:12])
        eid = id_empresa or self.EMP_DEFECTO
        self._exec(
            "INSERT INTO articulos (codigo, nombre, precio, Stock_total, Stock_tienda, id_empresa) "
            "VALUES (%s,%s,%s,%s,%s,%s)", (codigo, nombre, precio, stock_total, stock_tienda, eid))
        self._borrar("articulos", "codigo", codigo)
        return codigo

    def categoria(self, nombre="Cat Test", parent_id=None, id_empresa=None):
        from src.db import catalogo as cat
        cid = cat.crear_categoria(nombre, parent_id=parent_id, id_empresa=id_empresa or self.EMP_DEFECTO)
        self._borrar("catalogo_categorias", "id", cid)
        return cid

    def marca(self, nombre="Marca Test", id_empresa=None):
        from src.db import catalogo as cat
        mid = cat.crear_marca(nombre, id_empresa=id_empresa or self.EMP_DEFECTO)
        self._borrar("catalogo_marcas", "id", mid)
        return mid

    def producto_catalogo(self, codigo_articulo, id_empresa=None, **campos):
        from src.db import catalogo as cat
        eid = id_empresa or self.EMP_DEFECTO
        pid = cat.upsert_producto(codigo_articulo, id_empresa=eid, **campos)
        self.al_limpiar(lambda: cat.eliminar_producto(pid, id_empresa=eid))
        return pid

    def pedido_online(self, id_empresa=None, total=10.0, estado="PENDIENTE",
                      referencia_pago=None, referencia_externa=None, cliente_email=None):
        eid = id_empresa or self.EMP_DEFECTO
        pid = str(uuid.uuid4())
        self._exec(
            "INSERT INTO pedidos_online (id_pedido, id_empresa, total, estado, plataforma, "
            "referencia_pago, referencia_externa, cliente_email, estado_pago) "
            "VALUES (%s,%s,%s,%s,'web',%s,%s,%s,'pendiente')",
            (pid, eid, total, estado, referencia_pago, referencia_externa, cliente_email))
        # Limpieza: items, registro documental, webhooks y el propio pedido.
        def _limpia():
            self._exec("DELETE FROM pedidos_online_items WHERE id_pedido=%s", (pid,))
            self._exec("DELETE FROM documentos_registro WHERE referencia=%s", (pid,))
            self._exec("DELETE FROM pagos_webhooks_log WHERE id_pedido=%s", (pid,))
            self._exec("DELETE FROM pedidos_online WHERE id_pedido=%s", (pid,))
        self.al_limpiar(_limpia)
        return pid

    def pasarela(self, id_empresa=None, proveedor="simulado", **cfg):
        from src.db import pagos
        eid = id_empresa or self.EMP_DEFECTO
        pagos.guardar_config(proveedor=proveedor, id_empresa=eid, **cfg)
        self._borrar("pasarela_config", "id_empresa", eid)
        return eid

    def web(self, id_empresa=None, activa=1, **cfg):
        from src.db import web_tienda
        eid = id_empresa or self.EMP_DEFECTO
        web_tienda.guardar_config(activa=activa, id_empresa=eid, **cfg)
        self._borrar("web_config", "id_empresa", eid)
        return eid

    def usuario(self, nombre=None, password="Contrasena_Larga_123", perfil="OPERARIO",
                id_empresa=None, tienda_id=None, hash_legado=False):
        """Crea un usuario. Si `hash_legado=True`, guarda el password con SHA-256
        antiguo (para probar la migración); si no, con Argon2id."""
        import hashlib
        from src.seguridad import passwords as _pw
        nombre = nombre or ("USR_" + uuid.uuid4().hex[:8].upper())
        eid = id_empresa or self.EMP_DEFECTO
        ph = (hashlib.sha256(password.encode()).hexdigest() if hash_legado
              else _pw.hash_password(password))
        # id_empresa puede no existir como columna en instalaciones antiguas.
        with self.cx.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM usuarios")
            cols = [c[0] if not isinstance(c, dict) else c["Field"] for c in cur.fetchall()]
            if "id_empresa" in cols:
                cur.execute("INSERT INTO usuarios (nombre, password, perfil, tienda_id, id_empresa) "
                            "VALUES (%s,%s,%s,%s,%s)", (nombre, ph, perfil, tienda_id, eid))
            else:
                cur.execute("INSERT INTO usuarios (nombre, password, perfil, tienda_id) "
                            "VALUES (%s,%s,%s,%s)", (nombre, ph, perfil, tienda_id))
            uid = cur.lastrowid
            conn.commit()
        self._borrar("usuarios", "id", uid)
        return {"id": uid, "nombre": nombre, "perfil": perfil, "password": password}

    def buzon_correo(self, id_empresa=None, direccion=None):
        from src.db import correo as correo_db
        eid = id_empresa or self.EMP_DEFECTO
        direccion = direccion or f"buzon{uuid.uuid4().hex[:6]}@test.com"
        cid = correo_db.crear_correo(direccion, proveedor="simulado", id_empresa=eid)
        self._exec("UPDATE correos_corporativos SET estado='activo' WHERE id_correo=%s", (cid,))
        self._borrar("correos_corporativos", "id_correo", cid)
        return cid
