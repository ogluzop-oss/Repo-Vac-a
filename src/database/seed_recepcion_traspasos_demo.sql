USE smart_manager_db;

INSERT INTO articulos (
    codigo,
    nombre,
    descripcion,
    precio,
    Stock_total,
    Stock_tienda,
    Stock_central,
    estado
) VALUES
    ('8437010000011', 'CAFETERA SMART 12T', 'Artículo de prueba para recepción y traspasos', 59.90, 25, 10, 15, 'activo'),
    ('8437010000012', 'JUEGO DE SARTENES PRO', 'Artículo de prueba para recepción y traspasos', 39.95, 18, 8, 10, 'activo'),
    ('8437010000013', 'BATIDORA POWER MIX', 'Artículo de prueba para recepción y traspasos', 29.50, 30, 12, 18, 'activo'),
    ('8437010000014', 'VAJILLA URBAN 18P', 'Artículo de prueba para recepción y traspasos', 44.00, 14, 6, 8, 'activo'),
    ('8437010000015', 'SET CUCHILLOS CHEF', 'Artículo de prueba para recepción y traspasos', 22.75, 40, 16, 24, 'activo')
ON DUPLICATE KEY UPDATE
    nombre = VALUES(nombre),
    descripcion = VALUES(descripcion),
    precio = VALUES(precio),
    Stock_total = VALUES(Stock_total),
    Stock_tienda = VALUES(Stock_tienda),
    Stock_central = VALUES(Stock_central),
    estado = VALUES(estado);
