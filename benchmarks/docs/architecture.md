# Benchmark Architecture: Loom vs FastAPI Native

## Objective
Measure equivalent API behavior for three scenarios:
1. Cursor list without `COUNT(*)`
2. Offset list with `COUNT(*)`
3. Detail endpoint with relations and derived fields

## Apps
- Loom app: `benchmarks/apps/loom_app.py`
- FastAPI native app: `benchmarks/apps/fastapi_native_app.py`

## Loom Profiles
Loom runs from YAML profiles:
- `benchmarks/config/loom/base.yaml`
- `benchmarks/config/loom/cache.yaml`
- `benchmarks/config/loom/observability.yaml`

## Data Models
The benchmark uses the same conceptual entities in both implementations.

### `BenchUser`
- `id: int`
- `name: str`
- `email: str`

### `BenchRecord`
- `id: int`
- `owner_id: int`
- `request_id: str`
- `full_name: str`
- `email: str`

### `BenchNote`
- `id: int`
- `record_id: int`
- `title: str`

## Loom `with_details` contract
For `GET /bench/records/{id}?profile=with_details`, Loom includes:
- relation `owner`
- relation `notes`
- projection `has_notes`
- projection `notes_count`
- projection `note_snippets`

## Endpoints
- `GET /bench/ping`
- `GET /bench/dataset`
- `GET /bench/records?pagination=cursor&limit=...`
- `GET /bench/records?pagination=offset&page=...&limit=...`
- `GET /bench/records/{record_id}?profile=with_details`

## Scenarios
- `list_cursor_no_count`
- `list_offset_with_count`
- `detail_with_profile`

## Seeded Dataset
Each target seeds deterministic data at startup:
- `seed_users`
- `seed_records`
- `notes_per_record`

Actual object counts are exposed via `GET /bench/dataset` and persisted in benchmark output JSON.

## Running
1. `make benchmark-isolated-up`
2. `make benchmark-isolated`
3. `make benchmark-isolated-down`

Raw output is written to `benchmarks/artifacts/raw/benchmark_external_<timestamp>.json`.
