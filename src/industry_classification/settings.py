from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class TaxonomyLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    short_description: str
    prompt_text: str
    enabled: bool = True


class TaxonomyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    labels: list[TaxonomyLabel] = Field(default_factory=list)


def _taxonomy_path() -> Path:
    return Path(__file__).with_name("taxonomy_config.yaml")


@lru_cache(maxsize=1)
def load_taxonomy() -> TaxonomyConfig:
    with _taxonomy_path().open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return TaxonomyConfig.model_validate(payload)

