# Bruno Collection (dummy-loom)

Coleccion Bruno para probar toda la API de tienda.

## Uso rapido

1. Levanta la API:

```bash
make up
```

2. Abre Bruno y carga la carpeta:

`bruno_collection/`

3. Selecciona el entorno:

`environments/local.bru`

4. Ejecuta la carpeta `01-store-flow` en orden (secuencial).

## Cobertura

- Smoke: `/docs`
- CRUD y flujo completo:
  - users
  - addresses
  - products (incluye paginacion cursor)
  - orders (offset en endpoints list)
  - order-items
- Seed de datos para pruebas de filtros:
  - `07-seed-products` (crea varios productos con categorias/precios/stocks distintos)
- Query filters:
  - `08-query-filters` (eq, lte, combinados y cursor con filtro)

## Variables

La carpeta de flujo va guardando IDs en variables:

- `userId`
- `addressId`
- `productId`
- `orderId`
- `orderItemId`
- `cursor`

## Flujo recomendado para filtros

1. Ejecuta `07-seed-products` completo.
2. Ejecuta `08-query-filters` completo.
3. Si repites seed sin resetear DB, pueden fallar por `sku` duplicado.
