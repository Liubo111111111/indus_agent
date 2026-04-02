from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RuntimeConfig:
    worker_count: int = 4
    provider_rate_limit_per_minute: int = 120
    timeout_seconds: int = 30
    retry_limit: int = 1

