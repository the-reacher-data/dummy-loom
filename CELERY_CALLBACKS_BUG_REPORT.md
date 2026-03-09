# Bug Report: Callbacks de Celery no se ejecutan y workflow `/workflows/restock` falla con broker

Fecha: 2026-03-09

## Resumen
Hay **dos problemas distintos** al ejecutar `dummy-loom` con `CeleryJobService` (broker Redis):

1. `POST /products/{id}/workflows/restock` devuelve `500`.
2. Los callbacks `RestockEmailSuccessCallback` / `RestockEmailFailureCallback` **no se ejecutan**, aunque el job principal sí se procesa.

---

## Bug 1: `workflows/restock` falla en modo Celery

### Síntoma
`POST /products/{id}/workflows/restock` responde:

```json
{"code":"internal_error","message":"An unexpected error occurred","trace_id":null}
```

### Evidencia en logs API
Error real:

- `NotImplementedError: CeleryJobService.run() is not supported. Use dispatch()...`

El stack muestra que el fallo viene de `BuildProductSummaryUseCase` invocado dentro de `RestockWorkflowUseCase`.

### Causa
`BuildProductSummaryUseCase` usa `job_service.run(...)`, y en `CeleryJobService` ese método está explícitamente no soportado.

### Impacto
El workflow con callbacks no se puede usar cuando hay broker real (`celery` configurado).

---

## Bug 2: callbacks no se consumen (quedan en cola `celery`)

### Síntoma
`POST /products/{id}/jobs/restock-email` retorna `202` y el worker ejecuta `SendRestockEmailJob`, pero:

- no aparecen tareas `loom.callback.*` ejecutadas en logs,
- no se observan cambios esperados de callback sobre el producto (ej. sufijo de categoría),
- en Redis quedan mensajes en la cola `celery`.

### Evidencia
En Redis DB del broker (`/1`):

- `LLEN celery = 3`
- `LLEN default = 0`
- `LLEN notifications = 0`

Y la config del worker declara colas:

- `default, notifications, analytics, erp`

No incluye `celery`.

### Causa raíz probable
Las firmas de callback (`link`/`link_error`) se crean sin cola explícita y se enrutan a la cola por defecto de Celery (`celery`).
El worker de `dummy-loom` no consume esa cola, por lo que las callbacks quedan pendientes.

### Impacto
Se rompe la semántica de callbacks en producción: el job principal funciona, pero los efectos secundarios de callback no ocurren.

---

## Reproducción mínima

1. Levantar stack:

```bash
make up
```

2. Crear producto:

```bash
curl -X POST http://127.0.0.1:8000/products/ \
  -H 'content-type: application/json' \
  -d '{"sku":"cb-test-1","name":"CB","category":"cb","price_cents":1000,"stock":0}'
```

3. Disparar restock con callback:

```bash
curl -X POST http://127.0.0.1:8000/products/1/jobs/restock-email \
  -H 'content-type: application/json' \
  -d '{"recipient_email":"qa@example.com","force_fail":false}'
```

4. Verificar colas:

```bash
docker compose exec -T redis redis-cli -n 1 LLEN celery
docker compose exec -T redis redis-cli -n 1 LLEN default
```

Resultado actual: `celery > 0`, `default = 0`.

5. Repro del workflow roto:

```bash
curl -X POST http://127.0.0.1:8000/products/1/workflows/restock \
  -H 'content-type: application/json' \
  -d '{"recipient_email":"qa@example.com","force_fail":false}'
```

Resultado actual: `500 internal_error`.

---

## Criterio de validación del fix

### Para Bug 1
- `POST /products/{id}/workflows/restock` debe devolver `202` en modo Celery.
- No debe aparecer `NotImplementedError: CeleryJobService.run()` en logs.

### Para Bug 2
- Después de despachar restock con callback:
  - se deben observar tareas `loom.callback.*` / `loom.callback_error.*` consumidas por worker,
  - `LLEN celery` no debe crecer por callbacks pendientes,
  - debe verse el efecto esperado de callback en el producto (o logs explícitos de callback ejecutado).

---

## Notas de solución (orientativas)

1. Workflow:
- Evitar `job_service.run()` cuando el backend es Celery.
- O usar sólo `dispatch()` en modo broker.

2. Callbacks:
- Asegurar cola consumida para callbacks (p.ej. `default`) o configurar `task_default_queue` consistente.
- Alternativamente, incluir `celery` en `celery.queues` del worker.

