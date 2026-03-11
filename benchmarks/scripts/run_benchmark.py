"""Run a rigorous local benchmark against Loom and FastAPI native apps."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "benchmarks" / "raw"

DEFAULT_REPEATS = int(os.getenv("BENCH_REPEATS", "3"))
DEFAULT_WARMUP = int(os.getenv("BENCH_WARMUP", "200"))
DEFAULT_SEED_RECORDS = int(os.getenv("BENCH_SEED_RECORDS", "1000"))

BENCH_POSTGRES_DSN = os.getenv(
    "BENCH_POSTGRES_DSN",
    "postgresql+asyncpg://store:store@127.0.0.1:5432/store",
)


@dataclass(frozen=True)
class Scenario:
    """Benchmark scenario definition."""

    name: str
    requests: int
    concurrencies: tuple[int, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(name="ping", requests=4000, concurrencies=(20, 100, 300)),
    Scenario(name="insert", requests=1500, concurrencies=(10, 40, 80)),
    Scenario(name="get_by_id", requests=4000, concurrencies=(20, 100, 300)),
    Scenario(name="pricing_preview_input_compute", requests=3200, concurrencies=(20, 100, 300)),
)


def _percentile(sorted_values: list[float], q: float) -> float:
    """Return percentile for an already sorted list using nearest-rank."""

    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, int((len(sorted_values) - 1) * q)))
    return sorted_values[idx]


def _detect_uvicorn_runtime() -> tuple[str, str]:
    """Pick fastest available uvicorn runtime stack."""

    try:
        import uvloop  # noqa: F401
        import httptools  # noqa: F401

        return "uvloop", "httptools"
    except Exception:
        return "asyncio", "h11"


def _start_server(
    module_path: str,
    port: int,
    loop_impl: str,
    http_impl: str,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    return subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            module_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
            "--loop",
            loop_impl,
            "--http",
            http_impl,
            "--no-access-log",
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
    )


async def _wait_ready(base_url: str, timeout_s: float = 10.0) -> None:
    end = time.monotonic() + timeout_s
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.monotonic() < end:
            try:
                response = await client.get(f"{base_url}/bench/ping")
                if response.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.2)
    raise RuntimeError(f"Server not ready: {base_url}/bench/ping")


async def _seed_records(client: httpx.AsyncClient, base_url: str, seed_count: int) -> None:
    """Insert baseline rows so get_by_id can hit existing ids."""

    for idx in range(seed_count):
        response = await client.post(
            f"{base_url}/bench/insert",
            json={
                "request_id": f"seed-{idx}",
                "full_name": f"seed-{idx}",
                "email": f"seed-{idx}@example.com",
            },
        )
        if response.status_code not in {200, 201}:
            raise RuntimeError(f"Failed seeding benchmark data ({response.status_code})")


def _scenario_request(index: int, scenario_name: str, existing_records: int) -> tuple[str, str, dict[str, Any], set[int]]:
    """Build request tuple for one benchmark operation."""

    if scenario_name == "ping":
        return ("GET", "/bench/ping", {}, {200})

    if scenario_name == "insert":
        body = {
            "request_id": f"run-{index}",
            "full_name": f"user-{index}",
            "email": f"run-{index}@example.com",
        }
        return ("POST", "/bench/insert", {"json": body}, {200, 201})

    if scenario_name == "pricing_preview_input_compute":
        country = ("US", "ES", "DE", "FR")[index % 4]
        coupon = (None, "VIP5", "WELCOME10", "SHIPFREE")[index % 4]
        body = {
            "email": f" User{index}@Example.Com ",
            "country": country,
            "unit_price": float((index % 90) + 10),
            "quantity": (index % 5) + 1,
            "discount_pct": float(index % 20),
            "coupon_code": coupon,
            "vip": index % 2 == 0,
        }
        return ("POST", "/bench/pricing/preview", {"json": body}, {200})

    record_id = (index % existing_records) + 1
    return ("GET", f"/bench/records/{record_id}", {}, {200})


async def _run_scenario(
    client: httpx.AsyncClient,
    base_url: str,
    scenario: Scenario,
    concurrency: int,
    existing_records: int,
) -> dict[str, Any]:
    """Execute one scenario/concurrency run and collect metrics."""

    latencies_ms: list[float] = []
    status_codes: dict[str, int] = {}
    errors = 0
    semaphore = asyncio.Semaphore(concurrency)

    async def one_call(i: int) -> None:
        nonlocal errors

        method, path, kwargs, expected = _scenario_request(i, scenario.name, existing_records)
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.request(method=method, url=f"{base_url}{path}", **kwargs)
                code = str(response.status_code)
                status_codes[code] = status_codes.get(code, 0) + 1
                if response.status_code not in expected:
                    errors += 1
            except Exception:
                status_codes["exception"] = status_codes.get("exception", 0) + 1
                errors += 1
            finally:
                latencies_ms.append((time.perf_counter() - started) * 1000.0)

    started_total = time.perf_counter()
    await asyncio.gather(*(one_call(i) for i in range(scenario.requests)))
    duration_s = time.perf_counter() - started_total

    latencies_ms.sort()
    success = scenario.requests - errors

    return {
        "scenario": scenario.name,
        "requests": scenario.requests,
        "concurrency": concurrency,
        "duration_s": duration_s,
        "rps": scenario.requests / duration_s,
        "success": success,
        "errors": errors,
        "error_rate": errors / scenario.requests,
        "status_codes": status_codes,
        "latency_ms": {
            "min": latencies_ms[0],
            "p50": median(latencies_ms),
            "p95": _percentile(latencies_ms, 0.95),
            "p99": _percentile(latencies_ms, 0.99),
            "max": latencies_ms[-1],
        },
    }


def _aggregate_runs(raw_runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate repeated runs by scenario and concurrency using medians."""

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for run in raw_runs:
        key = (str(run["scenario"]), int(run["concurrency"]))
        grouped.setdefault(key, []).append(run)

    aggregates: list[dict[str, Any]] = []
    for (scenario_name, concurrency), runs in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        rps_values = [float(r["rps"]) for r in runs]
        error_rate_values = [float(r["error_rate"]) for r in runs]
        p50_values = [float(r["latency_ms"]["p50"]) for r in runs]
        p95_values = [float(r["latency_ms"]["p95"]) for r in runs]
        p99_values = [float(r["latency_ms"]["p99"]) for r in runs]

        aggregates.append(
            {
                "scenario": scenario_name,
                "concurrency": concurrency,
                "repeats": len(runs),
                "median_rps": median(rps_values),
                "median_error_rate": median(error_rate_values),
                "median_p50_ms": median(p50_values),
                "median_p95_ms": median(p95_values),
                "median_p99_ms": median(p99_values),
            }
        )

    return {"by_scenario": aggregates}


async def _benchmark_one(
    target: dict[str, Any],
    loop_impl: str,
    http_impl: str,
    repeats: int,
    warmup_calls: int,
    seed_records: int,
) -> dict[str, Any]:
    name = str(target["name"])
    module = str(target["module"])
    port = int(target["port"])

    env_overrides = target.get("env", None)
    proc = _start_server(
        module,
        port,
        loop_impl=loop_impl,
        http_impl=http_impl,
        env_overrides=env_overrides,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        await _wait_ready(base_url)

        raw_runs: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            await _seed_records(client, base_url, seed_records)

            for repeat in range(1, repeats + 1):
                for scenario in SCENARIOS:
                    for concurrency in scenario.concurrencies:
                        warmup = Scenario(name=scenario.name, requests=warmup_calls, concurrencies=(concurrency,))
                        await _run_scenario(client, base_url, warmup, concurrency, existing_records=seed_records)

                        result = await _run_scenario(
                            client,
                            base_url,
                            scenario,
                            concurrency,
                            existing_records=seed_records,
                        )
                        result["repeat"] = repeat
                        raw_runs.append(result)

        return {
            "target": name,
            "runtime": {"loop": loop_impl, "http": http_impl, "workers": 1},
            "raw_runs": raw_runs,
            "aggregate": _aggregate_runs(raw_runs),
        }
    finally:
        proc.terminate()
        proc.wait(timeout=5)


async def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        {
            "name": "loom",
            "module": "benchmarks.apps.loom_app:app",
            "port": 8101,
            "env": {
                "BENCH_CACHE_ENABLED": "0",
                "BENCH_LOOM_DATABASE_URL": BENCH_POSTGRES_DSN,
            },
        },
        {
            "name": "loom-cache",
            "module": "benchmarks.apps.loom_app:app",
            "port": 8103,
            "env": {
                "BENCH_CACHE_ENABLED": "1",
                "BENCH_LOOM_DATABASE_URL": BENCH_POSTGRES_DSN,
            },
        },
        {
            "name": "fastapi-native",
            "module": "benchmarks.apps.fastapi_native_app:app",
            "port": 8102,
            "env": {
                "BENCH_NATIVE_DATABASE_URL": BENCH_POSTGRES_DSN,
            },
        },
    ]

    loop_impl, http_impl = _detect_uvicorn_runtime()

    results: list[dict[str, Any]] = []
    for target in targets:
        result = await _benchmark_one(
            target,
            loop_impl=loop_impl,
            http_impl=http_impl,
            repeats=DEFAULT_REPEATS,
            warmup_calls=DEFAULT_WARMUP,
            seed_records=DEFAULT_SEED_RECORDS,
        )
        results.append(result)

    ts = int(time.time())
    output = {
        "timestamp": ts,
        "runtime": {"loop": loop_impl, "http": http_impl, "workers": 1},
        "methodology": {
            "repeats": DEFAULT_REPEATS,
            "warmup_calls": DEFAULT_WARMUP,
            "seed_records": DEFAULT_SEED_RECORDS,
            "scenarios": [
                {
                    "name": s.name,
                    "requests": s.requests,
                    "concurrencies": list(s.concurrencies),
                }
                for s in SCENARIOS
            ],
        },
        "results": results,
    }

    out_file = RAW_DIR / f"benchmark_{ts}.json"
    out_file.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(json.dumps(output, indent=2))
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
