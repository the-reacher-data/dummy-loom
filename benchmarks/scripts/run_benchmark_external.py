"""Run isolated benchmark matrix against external services."""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Callable

import httpx

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "benchmarks" / "raw"

DEFAULT_REPEATS = int(os.getenv("BENCH_REPEATS", "3"))
# 200 calls per scenario × concurrency level before each measured run.
# Ensures connection pools are fully saturated and DB plan caches are warm
# before any measurement starts (was 25, which left pools partially cold).
DEFAULT_WARMUP = int(os.getenv("BENCH_WARMUP", "200"))
REQUEST_SCALE = float(os.getenv("BENCH_REQUEST_SCALE", "1.0"))
MIN_REQUESTS_PER_SCENARIO = int(os.getenv("BENCH_MIN_REQUESTS", "1000"))
RANDOMIZE_TARGET_ORDER = os.getenv("BENCH_RANDOMIZE_TARGET_ORDER", "1") not in {"0", "false", "False"}
RANDOM_SEED = int(os.getenv("BENCH_RANDOM_SEED", "0")) or int(time.time())
RECORD_ID_RANGE_MIN = int(os.getenv("BENCH_RECORD_ID_MIN", "1"))
RECORD_ID_RANGE_MAX = int(os.getenv("BENCH_RECORD_ID_MAX", "100"))
PAGE_SIZE = int(os.getenv("BENCH_PAGE_SIZE", "25"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("BENCH_HTTP_TIMEOUT_SECONDS", "10.0"))
READY_TIMEOUT_SECONDS = float(os.getenv("BENCH_READY_TIMEOUT_SECONDS", "45.0"))
PROGRESS_LOG = os.getenv("BENCH_PROGRESS_LOG", "1") not in {"0", "false", "False"}
CONCURRENCY_VALUES = tuple(
    int(value.strip())
    for value in os.getenv("BENCH_CONCURRENCIES", "20,100,300").split(",")
    if value.strip()
)
if not CONCURRENCY_VALUES:
    raise RuntimeError("BENCH_CONCURRENCIES must define at least one integer value")


def _selected_scenarios() -> tuple[str, ...] | None:
    raw = os.getenv("BENCH_SCENARIOS", "").strip()
    if not raw:
        return None
    items = tuple(part.strip() for part in raw.split(",") if part.strip())
    return items or None


SELECTED_SCENARIOS = _selected_scenarios()


@dataclass(frozen=True)
class Scenario:
    """One benchmark scenario with fixed load profile."""

    name: str
    requests: int
    concurrencies: tuple[int, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="ping",
        requests=max(MIN_REQUESTS_PER_SCENARIO, int(3000 * REQUEST_SCALE)),
        concurrencies=CONCURRENCY_VALUES,
    ),
    Scenario(
        name="get_by_id_with_details",
        requests=max(MIN_REQUESTS_PER_SCENARIO, int(3000 * REQUEST_SCALE)),
        concurrencies=CONCURRENCY_VALUES,
    ),
    Scenario(
        name="list_cursor_no_count",
        requests=max(MIN_REQUESTS_PER_SCENARIO, int(2200 * REQUEST_SCALE)),
        concurrencies=CONCURRENCY_VALUES,
    ),
    Scenario(
        name="list_offset_with_count",
        requests=max(MIN_REQUESTS_PER_SCENARIO, int(2200 * REQUEST_SCALE)),
        concurrencies=CONCURRENCY_VALUES,
    ),
    Scenario(
        name="update_autocrud_plain",
        requests=max(MIN_REQUESTS_PER_SCENARIO, int(2200 * REQUEST_SCALE)),
        concurrencies=CONCURRENCY_VALUES,
    ),
)
if SELECTED_SCENARIOS is not None:
    selected_set = set(SELECTED_SCENARIOS)
    filtered = tuple(s for s in SCENARIOS if s.name in selected_set)
    if not filtered:
        allowed = ", ".join(s.name for s in SCENARIOS)
        raise RuntimeError(
            "BENCH_SCENARIOS did not match any known scenario. "
            f"Allowed values: {allowed}"
        )
    SCENARIOS = filtered


TARGETS: tuple[tuple[str, str], ...] = (
    ("loompy", os.getenv("BENCH_LOOM_BASE_URL", "http://127.0.0.1:8101")),
    ("loompy-cache-memory", os.getenv("BENCH_LOOM_CACHE_URL", "http://127.0.0.1:8103")),
    ("fastapi-native", os.getenv("BENCH_FASTAPI_URL", "http://127.0.0.1:8102")),
)


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, int((len(sorted_values) - 1) * q)))
    return sorted_values[idx]


async def _wait_ready(base_url: str, timeout_s: float = READY_TIMEOUT_SECONDS) -> None:
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


async def _warmup_connection_pool(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    calls: int = 500,
    concurrency: int = 20,
) -> None:
    """Pre-open all DB connections by firing ping requests before any scenario.

    SQLAlchemy opens pool connections lazily. Without this phase the first
    scenario sees connection-establishment overhead that inflates p99 and
    distorts RPS. 500 pings at c=20 is enough to saturate pool_size=5 +
    max_overflow=10 with margin.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _one() -> None:
        async with semaphore:
            try:
                await client.get(f"{base_url}/bench/ping")
            except Exception:
                pass

    await asyncio.gather(*(_one() for _ in range(calls)))


async def _fetch_dataset_summary(client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    response = await client.get(f"{base_url}/bench/dataset")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Invalid dataset payload")
    return payload


def _pick_record_id(*, max_record_id: int, rng: random.Random) -> int:
    lower = max(1, RECORD_ID_RANGE_MIN)
    configured_upper = RECORD_ID_RANGE_MAX if RECORD_ID_RANGE_MAX > 0 else max_record_id
    upper = min(max_record_id, configured_upper)
    if lower > upper:
        raise RuntimeError(
            "Invalid record id interval: "
            f"BENCH_RECORD_ID_MIN={RECORD_ID_RANGE_MIN} must be <= "
            f"effective max ({upper})"
        )
    return rng.randint(lower, upper)


def _scenario_request(
    index: int,
    scenario_name: str,
    max_record_id: int,
    rng: random.Random,
) -> tuple[str, str, dict[str, Any], set[int]]:
    record_id = _pick_record_id(max_record_id=max_record_id, rng=rng)
    if scenario_name == "ping":
        return ("GET", "/bench/ping", {}, {200})

    if scenario_name == "get_by_id_with_details":
        return ("GET", f"/bench/records/{record_id}?profile=with_details", {}, {200})
    if scenario_name == "list_cursor_no_count":
        return ("GET", f"/bench/records?pagination=cursor&limit={PAGE_SIZE}", {}, {200})
    if scenario_name == "list_offset_with_count":
        total_pages = max(1, (max_record_id + PAGE_SIZE - 1) // PAGE_SIZE)
        page = (index % total_pages) + 1
        return (
            "GET",
            f"/bench/records?pagination=offset&page={page}&limit={PAGE_SIZE}",
            {},
            {200},
        )

    if scenario_name == "pricing_preview_input_compute":
        country = ("US", "ES", "DE", "FR")[index % 4]
        coupon = (None, "VIP5", "WELCOME10", "SHIPFREE")[index % 4]
        return (
            "POST",
            f"/bench/records/{record_id}/pricing-preview",
            {
                "json": {
                    "email": f" User{index}@Example.Com ",
                    "country": country,
                    "unit_price": float((index % 90) + 10),
                    "quantity": (index % 5) + 1,
                    "discount_pct": float(index % 20),
                    "coupon_code": coupon,
                    "vip": index % 2 == 0,
                }
            },
            {200},
        )

    if scenario_name == "update_autocrud_plain":
        return (
            "PATCH",
            f"/bench/records/{record_id}",
            {"json": {"email": f"record-{record_id}-{index}@example.com"}},
            {200},
        )

    raise RuntimeError(f"Unknown scenario: {scenario_name}")


async def _run_scenario(
    client: httpx.AsyncClient,
    base_url: str,
    scenario: Scenario,
    concurrency: int,
    max_record_id: int,
    rng: random.Random,
) -> dict[str, Any]:
    latencies_ms: list[float] = []
    status_codes: dict[str, int] = {}
    errors = 0
    semaphore = asyncio.Semaphore(concurrency)

    async def one_call(i: int) -> None:
        nonlocal errors
        async with semaphore:
            started = time.perf_counter()
            try:
                method, path, kwargs, expected = _scenario_request(i, scenario.name, max_record_id, rng)
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
    return {
        "scenario": scenario.name,
        "requests": scenario.requests,
        "concurrency": concurrency,
        "duration_s": duration_s,
        "rps": scenario.requests / duration_s,
        "success": scenario.requests - errors,
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
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for run in raw_runs:
        grouped.setdefault((str(run["scenario"]), int(run["concurrency"])), []).append(run)

    aggregates: list[dict[str, Any]] = []
    for (scenario_name, concurrency), runs in sorted(grouped.items(), key=lambda i: (i[0][0], i[0][1])):
        aggregates.append(
            {
                "scenario": scenario_name,
                "concurrency": concurrency,
                "repeats": len(runs),
                "median_rps": median(float(r["rps"]) for r in runs),
                "median_error_rate": median(float(r["error_rate"]) for r in runs),
                "median_p50_ms": median(float(r["latency_ms"]["p50"]) for r in runs),
                "median_p95_ms": median(float(r["latency_ms"]["p95"]) for r in runs),
                "median_p99_ms": median(float(r["latency_ms"]["p99"]) for r in runs),
            }
        )
    return {"by_scenario": aggregates}


def _write_snapshot(output: dict[str, Any], out_file: Path) -> None:
    tmp_file = out_file.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    tmp_file.replace(out_file)


def _log_progress(
    *,
    target: str,
    scenario: str,
    concurrency: int,
    repeat: int,
    completed: int,
    total: int,
    started_at: float,
    result: dict[str, Any],
) -> None:
    if not PROGRESS_LOG:
        return
    elapsed = time.monotonic() - started_at
    print(
        "[progress] "
        f"{completed}/{total} "
        f"target={target} repeat={repeat} scenario={scenario} conc={concurrency} "
        f"rps={float(result['rps']):.2f} err={int(result['errors'])} "
        f"elapsed_s={elapsed:.1f}",
        flush=True,
    )


async def _benchmark_one(
    name: str,
    base_url: str,
    repeats: int,
    warmup_calls: int,
    target_result: dict[str, Any],
    progress_state: dict[str, int],
    total_measurements: int,
    started_at: float,
    save_snapshot: Callable[[], None],
) -> None:
    await _wait_ready(base_url)

    raw_runs: list[dict[str, Any]] = target_result["raw_runs"]
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        dataset = await _fetch_dataset_summary(client, base_url)
        target_result["dataset"] = dataset
        rng = random.Random(RANDOM_SEED)
        max_record_id = int(dataset.get("records", 0))
        if max_record_id <= 0:
            raise RuntimeError(f"Dataset for target {name} has no records")

        # Pre-open all DB connections before any scenario runs.
        # Without this, cold pool connections inflate early measurements.
        await _warmup_connection_pool(client, base_url)

        for repeat in range(1, repeats + 1):
            for scenario in SCENARIOS:
                for concurrency in scenario.concurrencies:
                    warmup = Scenario(name=scenario.name, requests=warmup_calls, concurrencies=(concurrency,))
                    await _run_scenario(
                        client,
                        base_url,
                        warmup,
                        concurrency,
                        max_record_id=max_record_id,
                        rng=rng,
                    )
                    result = await _run_scenario(
                        client,
                        base_url,
                        scenario,
                        concurrency,
                        max_record_id=max_record_id,
                        rng=rng,
                    )
                    result["repeat"] = repeat
                    raw_runs.append(result)
                    target_result["aggregate"] = _aggregate_runs(raw_runs)

                    progress_state["completed"] += 1
                    _log_progress(
                        target=name,
                        scenario=scenario.name,
                        concurrency=concurrency,
                        repeat=repeat,
                        completed=progress_state["completed"],
                        total=total_measurements,
                        started_at=started_at,
                        result=result,
                    )
                    save_snapshot()


async def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    targets = list(TARGETS)
    if RANDOMIZE_TARGET_ORDER:
        random.Random(RANDOM_SEED).shuffle(targets)

    started_at = time.monotonic()
    total_measurements = len(targets) * DEFAULT_REPEATS * sum(len(s.concurrencies) for s in SCENARIOS)
    ts = int(time.time())

    output: dict[str, Any] = {
        "timestamp": ts,
        "runtime": {"mode": "external", "workers": 1},
        "methodology": {
            "repeats": DEFAULT_REPEATS,
            "warmup_calls": DEFAULT_WARMUP,
            "randomized_target_order": RANDOMIZE_TARGET_ORDER,
            "random_seed": RANDOM_SEED,
            "target_order": [name for name, _ in targets],
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "ready_timeout_seconds": READY_TIMEOUT_SECONDS,
            "scenarios": [
                {"name": s.name, "requests": s.requests, "concurrencies": list(s.concurrencies)}
                for s in SCENARIOS
            ],
            "record_id_interval": {
                "min": RECORD_ID_RANGE_MIN,
                "max": RECORD_ID_RANGE_MAX,
            },
        },
        "results": [],
    }

    out_file = RAW_DIR / f"benchmark_external_{ts}.json"

    def save_snapshot() -> None:
        _write_snapshot(output, out_file)

    save_snapshot()

    progress_state: dict[str, int] = {"completed": 0}
    for name, base_url in targets:
        target_result: dict[str, Any] = {
            "target": name,
            "base_url": base_url,
            "runtime": {"mode": "external", "workers": 1},
            "dataset": {},
            "raw_runs": [],
            "aggregate": {"by_scenario": []},
        }
        output["results"].append(target_result)
        save_snapshot()

        await _benchmark_one(
            name=name,
            base_url=base_url,
            repeats=DEFAULT_REPEATS,
            warmup_calls=DEFAULT_WARMUP,
            target_result=target_result,
            progress_state=progress_state,
            total_measurements=total_measurements,
            started_at=started_at,
            save_snapshot=save_snapshot,
        )

    _write_snapshot(output, out_file)
    print(json.dumps(output, indent=2))
    print(f"Saved: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
