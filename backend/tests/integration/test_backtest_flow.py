"""集成测试：完整回溯流程端到端验证。

从标注加载 → 回溯执行 → 结果持久化 → 报告生成的完整流程。
Mock run_once 避免真实 LLM 调用。

Requirements: 1.1, 2.1, 2.5, 3.1, 7.1, 7.2
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from industry_classification.backtest_engine import BacktestConfig, BacktestEngine
from industry_classification.backtest_metrics import build_accuracy_report
from industry_classification.graph_state import GraphState
from industry_classification.schemas import DecisionRecord, WideRow
from industry_classification.writers.sqlite_store import SqliteResultStore


# ---------------------------------------------------------------------------
# 测试数据工厂
# ---------------------------------------------------------------------------

def _make_wide_row_dict(social_credit_code: str, enterprise_name: str) -> dict:
    """构造最小合法 WideRow 字典。"""
    return {
        "user_id": 1,
        "social_credit_code": social_credit_code,
        "enterprise_name": enterprise_name,
        "business_scope": "软件开发",
        "total_job_post_cnt_90d": 10,
        "distinct_job_name_cnt_90d": 3,
        "top_job_names": [],
        "jobs_recent_20": [],
        "latest_publish_time": None,
        "latest_publish_job_names": [],
        "authentication_time": None,
    }


def _make_graph_state(
    run_id: str,
    entity_key: str,
    wide_row_dict: dict,
    final_label: str,
    confidence: str = "high",
    error_type: str | None = None,
) -> GraphState:
    """构造带 decision_record 的 GraphState。"""
    wide_row = WideRow.model_validate(wide_row_dict)
    decision_record = DecisionRecord(
        final_label=final_label,
        confidence_level=confidence,
        low_confidence=confidence == "low",
        decision_reason=f"测试决策原因: {final_label}",
        supporting_evidence=["证据1"],
        conflict_note=None,
    )
    return GraphState(
        run_id=run_id,
        entity_key=entity_key,
        feature_schema_version="v1",
        taxonomy_version="v1",
        graph_version="v1",
        prompt_version_static="v1",
        prompt_version_dynamic="v1",
        prompt_version_final="v2",
        model_version_static="mock-static-v1",
        model_version_dynamic="mock-dynamic-v1",
        model_version_final="mock-final-v1",
        wide_row=wide_row,
        decision_record=decision_record,
        route="formal",
        error_type=error_type,
    )



# ---------------------------------------------------------------------------
# 数据库初始化辅助
# ---------------------------------------------------------------------------

def _seed_database(sqlite_path: Path) -> None:
    """向临时数据库插入 3 个企业的 pipeline_runs 和 annotations 数据。

    企业 A、B 标注为"信息技术"，企业 C 标注为"制造业"。
    pipeline_runs.created_at 设为 2025-01-15，对应 pt_date = "20250115"。
    """
    # 先用 SqliteResultStore 初始化 schema
    store = SqliteResultStore(sqlite_path)
    store.close()

    entities = [
        ("ENT_A", "测试企业A", "信息技术"),
        ("ENT_B", "测试企业B", "信息技术"),
        ("ENT_C", "测试企业C", "制造业"),
    ]

    conn = sqlite3.connect(str(sqlite_path))
    try:
        for i, (ek, name, label) in enumerate(entities):
            run_id = f"run-{ek}"
            wide_row = _make_wide_row_dict(ek, name)

            # 插入 pipeline_runs
            conn.execute(
                """
                INSERT INTO pipeline_runs (
                    run_id, entity_key, route, error_type,
                    feature_schema_version, taxonomy_version, graph_version,
                    prompt_version_static, prompt_version_dynamic, prompt_version_final,
                    model_version_static, model_version_dynamic, model_version_final,
                    wide_row_json, created_at, updated_at
                ) VALUES (?, ?, 'formal', NULL,
                    'v1', 'v1', 'v1', 'v1', 'v1', 'v2',
                    'mock-s', 'mock-d', 'mock-f',
                    ?, '2025-01-15 10:00:00', '2025-01-15 10:00:00')
                """,
                (run_id, ek, json.dumps(wide_row, ensure_ascii=False)),
            )

            # 插入 annotations
            conn.execute(
                """
                INSERT INTO annotations (
                    run_id, entity_key, annotated_label,
                    reviewer_notes, reviewer_name, created_at
                ) VALUES (?, ?, ?, '', 'tester', '2025-01-15 12:00:00')
                """,
                (run_id, ek, label),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 测试 1: 完整回溯流程端到端
# ---------------------------------------------------------------------------

def test_full_backtest_flow_end_to_end(tmp_path: Path) -> None:
    """验证从标注加载 → 回溯执行 → 结果持久化 → 报告生成的完整流程。

    企业 A、B 标注为"信息技术"，企业 C 标注为"制造业"。
    Mock run_once 让 A、B 预测"信息技术"（正确），C 预测"信息技术"（错误）。
    预期准确率 = 2/3。
    """
    sqlite_path = tmp_path / "test.sqlite3"
    _seed_database(sqlite_path)

    config = BacktestConfig(
        backtest_run_id="bt-test-001",
        pt_dates=["20250115"],
        prompt_version_static="v1",
        prompt_version_dynamic="v1",
        prompt_version_final="v2",
    )
    engine = BacktestEngine(sqlite_path=sqlite_path, config=config)

    # 验证数据集加载（Req 1.1）
    dataset = engine.load_annotation_dataset()
    assert len(dataset) == 3
    entity_keys = {r["entity_key"] for r in dataset}
    assert entity_keys == {"ENT_A", "ENT_B", "ENT_C"}

    # 构造 mock run_once：所有企业都预测"信息技术"
    def mock_run_once(row_dict, run_id, client, formal_store, fallback_store,
                      sqlite_store=None, sqlite_path=None, **kwargs):
        ek = row_dict["social_credit_code"]
        return _make_graph_state(
            run_id=run_id,
            entity_key=ek,
            wide_row_dict=row_dict,
            final_label="信息技术",
            confidence="high",
        )

    # Mock 掉 LLM 相关依赖，避免真实网络调用
    with (
        patch("industry_classification.backtest_engine.run_once", side_effect=mock_run_once),
        patch("industry_classification.backtest_engine.load_llm_settings") as mock_settings,
        patch("industry_classification.backtest_engine.HttpLLMClient") as mock_http_client,
    ):
        mock_settings.return_value = MagicMock()
        mock_http_client.return_value = MagicMock()

        # 执行回溯（Req 2.1）
        engine.run()

    # --- 验证持久化结果 ---
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        # 验证 backtest_runs 表（Req 7.1）
        run_row = conn.execute(
            "SELECT * FROM backtest_runs WHERE backtest_run_id = ?",
            ("bt-test-001",),
        ).fetchone()
        assert run_row is not None
        assert run_row["status"] == "done"
        assert run_row["dataset_size"] == 3
        assert run_row["completed_count"] == 3
        assert run_row["error_count"] == 0
        assert run_row["prompt_version_static"] == "v1"
        assert run_row["prompt_version_final"] == "v2"
        pt_dates = json.loads(run_row["pt_dates_json"])
        assert pt_dates == ["20250115"]

        # 验证 backtest_results 表（Req 7.2, 2.5）
        results = conn.execute(
            "SELECT * FROM backtest_results WHERE backtest_run_id = ? ORDER BY entity_key",
            ("bt-test-001",),
        ).fetchall()
        assert len(results) == 3

        result_map = {r["entity_key"]: dict(r) for r in results}
        # A: 标注=信息技术, 预测=信息技术 → 正确
        assert result_map["ENT_A"]["annotated_label"] == "信息技术"
        assert result_map["ENT_A"]["predicted_label"] == "信息技术"
        assert result_map["ENT_A"]["confidence_level"] == "high"
        assert result_map["ENT_A"]["error_type"] is None

        # C: 标注=制造业, 预测=信息技术 → 错误
        assert result_map["ENT_C"]["annotated_label"] == "制造业"
        assert result_map["ENT_C"]["predicted_label"] == "信息技术"

        # 验证 decision_record_json 包含完整字段（Req 7.4 相关）
        dr_json = json.loads(result_map["ENT_A"]["decision_record_json"])
        assert dr_json["final_label"] == "信息技术"
        assert dr_json["confidence_level"] == "high"
        assert "decision_reason" in dr_json

        # 验证准确率（Req 3.1）
        accuracy = run_row["accuracy"]
        assert abs(accuracy - 2.0 / 3.0) < 1e-9

        # 验证 build_accuracy_report 能正确处理存储的结果
        stored_results = [
            {
                "entity_key": r["entity_key"],
                "enterprise_name": "",
                "annotated_label": r["annotated_label"],
                "predicted_label": r["predicted_label"],
                "confidence_level": r["confidence_level"],
                "error_type": r["error_type"],
            }
            for r in results
        ]
        report = build_accuracy_report(stored_results)
        assert report.total == 3
        assert report.correct == 2
        assert report.error_count == 0
        assert abs(report.accuracy - 2.0 / 3.0) < 1e-9
        # 混淆矩阵应包含两个标注标签
        assert "信息技术" in report.confusion_matrix
        assert "制造业" in report.confusion_matrix
        # 错误分类明细应包含企业 C
        assert len(report.misclassified) == 1
        assert report.misclassified[0]["annotated_label"] == "制造业"
        assert report.misclassified[0]["predicted_label"] == "信息技术"

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 测试 2: LLM 错误不中断回溯
# ---------------------------------------------------------------------------

def test_backtest_handles_llm_errors(tmp_path: Path) -> None:
    """验证单条企业 LLM 调用失败时，回溯继续执行并正确记录错误。

    企业 B 的 run_once 抛出异常，A 和 C 正常返回。
    预期: completed_count=3, error_count=1, 准确率基于 A 和 C 计算。
    """
    sqlite_path = tmp_path / "test.sqlite3"
    _seed_database(sqlite_path)

    config = BacktestConfig(
        backtest_run_id="bt-test-err",
        pt_dates=["20250115"],
    )
    engine = BacktestEngine(sqlite_path=sqlite_path, config=config)

    def mock_run_once_with_error(row_dict, run_id, client, formal_store,
                                  fallback_store, sqlite_store=None,
                                  sqlite_path=None, **kwargs):
        ek = row_dict["social_credit_code"]
        if ek == "ENT_B":
            raise RuntimeError("模拟 LLM 调用超时")
        # A 预测"信息技术"（正确），C 预测"制造业"（正确）
        label = "信息技术" if ek == "ENT_A" else "制造业"
        return _make_graph_state(
            run_id=run_id,
            entity_key=ek,
            wide_row_dict=row_dict,
            final_label=label,
        )

    with (
        patch("industry_classification.backtest_engine.run_once", side_effect=mock_run_once_with_error),
        patch("industry_classification.backtest_engine.load_llm_settings") as mock_settings,
        patch("industry_classification.backtest_engine.HttpLLMClient") as mock_http_client,
    ):
        mock_settings.return_value = MagicMock()
        mock_http_client.return_value = MagicMock()

        engine.run()

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        # 验证运行记录
        run_row = conn.execute(
            "SELECT * FROM backtest_runs WHERE backtest_run_id = ?",
            ("bt-test-err",),
        ).fetchone()
        assert run_row is not None
        assert run_row["status"] == "done"
        assert run_row["completed_count"] == 3
        assert run_row["error_count"] == 1

        # 验证结果记录
        results = conn.execute(
            "SELECT * FROM backtest_results WHERE backtest_run_id = ? ORDER BY entity_key",
            ("bt-test-err",),
        ).fetchall()
        assert len(results) == 3

        result_map = {r["entity_key"]: dict(r) for r in results}

        # B 应有 error_type
        assert result_map["ENT_B"]["error_type"] == "RuntimeError"
        assert result_map["ENT_B"]["predicted_label"] is None

        # A 和 C 正常
        assert result_map["ENT_A"]["error_type"] is None
        assert result_map["ENT_C"]["error_type"] is None

        # 准确率应基于有效记录（A 和 C 都正确）= 1.0
        accuracy = run_row["accuracy"]
        assert abs(accuracy - 1.0) < 1e-9

    finally:
        conn.close()
