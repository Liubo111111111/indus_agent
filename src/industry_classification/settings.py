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


class PromptAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    system_prompt: str
    user_template: str


def _taxonomy_path() -> Path:
    return Path(__file__).with_name("taxonomy_config.yaml")


def _prompt_asset_path(node_name: str, version: str) -> Path:
    return Path(__file__).with_name("prompts") / f"{node_name}_{version}.yaml"


@lru_cache(maxsize=1)
def load_taxonomy() -> TaxonomyConfig:
    with _taxonomy_path().open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return TaxonomyConfig.model_validate(payload)


@lru_cache(maxsize=16)
def load_prompt_asset(node_name: str, version: str) -> PromptAsset:
    with _prompt_asset_path(node_name, version).open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return PromptAsset.model_validate(payload)
