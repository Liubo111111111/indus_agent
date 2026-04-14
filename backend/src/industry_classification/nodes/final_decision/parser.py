from __future__ import annotations

import logging

from industry_classification.llm.result_handler import normalize_llm_json
from industry_classification.schemas import DecisionRecord
from industry_classification.settings import load_taxonomy

logger = logging.getLogger(__name__)

# 加载合法标签集合（缓存）
_VALID_LABELS: set[str] | None = None


def _get_valid_labels() -> set[str]:
    global _VALID_LABELS
    if _VALID_LABELS is None:
        taxonomy = load_taxonomy()
        _VALID_LABELS = {label.display_name for label in taxonomy.labels if label.enabled}
    return _VALID_LABELS


class FinalDecisionParser:
    def parse(self, raw_text: str) -> DecisionRecord:
        result = normalize_llm_json(raw_text, schema_name="DecisionRecord", schema_model=DecisionRecord)
        if not result.ok or result.data is None:
            raise ValueError(result.error_type or "unknown_final_decision_error")
        record = DecisionRecord.model_validate(result.data)

        # 校验 final_label 是否在 taxonomy 合法标签内
        valid_labels = _get_valid_labels()
        if record.final_label not in valid_labels:
            original = record.final_label
            logger.warning(
                "final_label '%s' 不在 taxonomy 中，强制归为'其他'（合法标签: %s）",
                original, ", ".join(sorted(valid_labels)),
            )
            record = record.model_copy(update={
                "final_label": "其他",
                "confidence_level": "low",
                "low_confidence": True,
                "conflict_note": f"模型输出标签'{original}'不在合法 taxonomy 中，已强制归为'其他'",
            })

        return record
