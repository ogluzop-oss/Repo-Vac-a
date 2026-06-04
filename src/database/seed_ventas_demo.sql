-- ============================================================
-- DATOS DE DEMO — VENTAS (cubre todos los filtros de Ventas/Analítica)
-- Empleados: María, Carlos, Laura
-- Cajas: 1 y 2
-- Formas de pago: efectivo, tarjeta, cupón, tarjeta regalo
-- Secciones: HOGAR, COCINA, ELECTRODOMÉSTICOS, TEXTIL
-- Fechas: últimos 60 días (relativas a la fecha de inserción)
-- ============================================================

USE smart_manager_db;

-- ── Aseguramos que los artículos demo existen ─────────────────────────────────
INSERT INTO articulos (codigo, nombre, descripcion, precio, Stock_total, Stock_tienda, Stock_central, estado)
VALUES
  ('8437010000011', 'CAFETERA SMART 12T',    'Demo', 59.90, 25, 10, 15, 'activo'),
  ('8437010000012', 'JUEGO DE SARTENES PRO', 'Demo', 39.95, 18,  8, 10, 'activo'),
  ('8437010000013', 'BATIDORA POWER MIX',    'Demo', 29.50, 30, 12, 18, 'activo'),
  ('8437010000014', 'VAJILLA URBAN 18P',     'Demo', 44.00, 14,  6,  8, 'activo'),
  ('8437010000015', 'SET CUCHILLOS CHEF',    'Demo', 22.75, 40, 16, 24, 'activo'),
  ('8437010000016', 'TOALLA RIZO PREMIUM',   'Demo',  9.99, 60, 30, 30, 'activo'),
  ('8437010000017', 'FUNDA NÓRDICA 150',     'Demo', 34.50, 20, 10, 10, 'activo'),
  ('8437010000018', 'LICUADORA FRESH PRO',   'Demo', 49.90, 15,  7,  8, 'activo')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre), precio = VALUES(precio), estado = VALUES(estado);

-- ── Ventas ────────────────────────────────────────────────────────────────────
-- Ticket 1: efectivo, caja 1, María — hace 55 días, mañana 09:30
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 55 DAY) + INTERVAL '09:30:00' HOUR_SECOND, 89.85, 'efectivo', 'María', 1);

SET @v1 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v1, '8437010000011', 'CAFETERA SMART 12T',    'ELECTRODOMÉSTICOS', 1, 59.90, 59.90),
  (@v1, '8437010000015', 'SET CUCHILLOS CHEF',    'COCINA',             1, 22.75, 22.75),
  (@v1, '8437010000016', 'TOALLA RIZO PREMIUM',   'TEXTIL',             1,  9.99,  9.99);

-- Ticket 2: tarjeta, caja 2, Carlos — hace 48 días, 11:15
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 48 DAY) + INTERVAL '11:15:00' HOUR_SECOND, 44.00, 'tarjeta', 'Carlos', 2);

SET @v2 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v2, '8437010000014', 'VAJILLA URBAN 18P', 'HOGAR', 1, 44.00, 44.00);

-- Ticket 3: cupón, caja 1, Laura — hace 40 días, 16:45
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 40 DAY) + INTERVAL '16:45:00' HOUR_SECOND, 69.45, 'cupón', 'Laura', 1);

SET @v3 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v3, '8437010000012', 'JUEGO DE SARTENES PRO', 'COCINA', 1, 39.95, 39.95),
  (@v3, '8437010000016', 'TOALLA RIZO PREMIUM',   'TEXTIL', 3,  9.99, 29.97);

-- Ticket 4: tarjeta regalo, caja 2, María — hace 30 días, 10:00
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 30 DAY) + INTERVAL '10:00:00' HOUR_SECOND, 34.50, 'tarjeta regalo', 'María', 2);

SET @v4 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v4, '8437010000017', 'FUNDA NÓRDICA 150', 'HOGAR', 1, 34.50, 34.50);

-- Ticket 5: efectivo, caja 1, Carlos — hace 22 días, 12:30
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 22 DAY) + INTERVAL '12:30:00' HOUR_SECOND, 129.30, 'efectivo', 'Carlos', 1);

SET @v5 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v5, '8437010000011', 'CAFETERA SMART 12T',  'ELECTRODOMÉSTICOS', 1, 59.90,  59.90),
  (@v5, '8437010000018', 'LICUADORA FRESH PRO', 'ELECTRODOMÉSTICOS', 1, 49.90,  49.90),
  (@v5, '8437010000016', 'TOALLA RIZO PREMIUM', 'TEXTIL',            2,  9.99,  19.98);

-- Ticket 6: tarjeta, caja 2, Laura — hace 15 días, 17:00
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 15 DAY) + INTERVAL '17:00:00' HOUR_SECOND, 79.45, 'tarjeta', 'Laura', 2);

SET @v6 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v6, '8437010000013', 'BATIDORA POWER MIX',    'ELECTRODOMÉSTICOS', 1, 29.50, 29.50),
  (@v6, '8437010000014', 'VAJILLA URBAN 18P',     'HOGAR',             1, 44.00, 44.00),
  (@v6, '8437010000016', 'TOALLA RIZO PREMIUM',   'TEXTIL',            1,  9.99,  5.95);

-- Ticket 7: cupón, caja 1, María — hace 8 días, 09:00
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 8 DAY) + INTERVAL '09:00:00' HOUR_SECOND, 22.75, 'cupón', 'María', 1);

SET @v7 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v7, '8437010000015', 'SET CUCHILLOS CHEF', 'COCINA', 1, 22.75, 22.75);

-- Ticket 8: tarjeta regalo, caja 2, Carlos — hace 3 días, 14:20
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (DATE_SUB(NOW(), INTERVAL 3 DAY) + INTERVAL '14:20:00' HOUR_SECOND, 99.40, 'tarjeta regalo', 'Carlos', 2);

SET @v8 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v8, '8437010000018', 'LICUADORA FRESH PRO', 'ELECTRODOMÉSTICOS', 1, 49.90, 49.90),
  (@v8, '8437010000017', 'FUNDA NÓRDICA 150',   'HOGAR',             1, 34.50, 34.50),
  (@v8, '8437010000016', 'TOALLA RIZO PREMIUM', 'TEXTIL',            1,  9.99,  9.99);

-- Ticket 9: efectivo, caja 1, Laura — hoy, 10:45
INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja)
VALUES (NOW() - INTERVAL '10:45:00' HOUR_SECOND + INTERVAL 1 HOUR, 59.49, 'efectivo', 'Laura', 1);

SET @v9 = LAST_INSERT_ID();
INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) VALUES
  (@v9, '8437010000013', 'BATIDORA POWER MIX',  'ELECTRODOMÉSTICOS', 1, 29.50, 29.50),
  (@v9, '8437010000017', 'FUNDA NÓRDICA 150',   'HOGAR',             1, 34.50, 34.50);
