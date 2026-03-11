"""Manifest exports for Loom benchmark discovery."""

from benchmarks.apps.loom_components import (
    BenchNote,
    BenchRecordsAutoInterface,
    BenchRecordsCustomInterface,
    BenchOpsInterface,
    BenchRecord,
    BenchUser,
    DatasetSummaryUseCase,
    ListBenchRecordsUseCase,
    PingUseCase,
    PricingPreviewUseCase,
)

MODELS = [BenchUser, BenchRecord, BenchNote]
USE_CASES = [
    PingUseCase,
    ListBenchRecordsUseCase,
    DatasetSummaryUseCase,
    PricingPreviewUseCase,
]
INTERFACES = [BenchRecordsAutoInterface, BenchRecordsCustomInterface, BenchOpsInterface]
