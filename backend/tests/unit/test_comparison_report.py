"""ComparisonEngine.generate_report 单元测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from industry_classification.comparison_engine import ComparisonConfig, ComparisonEngine


def _create_test_db(tmp_path: Path) -> Path:
    """创建测试用 SQLite 数据库，包含 comparison_results 和 comparison_annotations 表。"""
    db_path = tmp_path / "test.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE comparison_results (
            session_id TEXT,
            entity_key TEXT,
            enterprise_name TEXT,
            old_label TEXT,
            new_label TEXT,
            confidence_level TEXT,
            decision_reason TEXT,
            decision_record_json TEXT,
            error_type TEXT,
            wide_row_json TEXT,
            static_profile_json TEXT,
            dynamic_profile_json TEXT,
            created_at TEXT,
            PRIMARY KEY (session_id, entity_key)
        )
    """)
    conn.execute("""
        CREATE TABLE comparison_annotations (
            session_id TEXT,
            entity_key TEXT,
            human_label TEXT,
            reviewer_name TEXT,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (session_id, entity_key)
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_results(db_path: Path, session_id: str, records: list[dict]) -> None:
    """向 comparison_results 表插入测试数据。"""
    conn = sqlite3.connect(str(db_path))
    for r in records:
        conn.execute(
            """
            INSERT INTO comparison_results
                (session_id, entity_key, enterprise_name, old_label, new_label,
                 confidence_level, decision_reason, error_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2024-01-01 00:00:00')
            """,
            (
                session_id,
                r["entity_key"],
                r.get("enterprise_name", ""),
                r["old_label"],
                r.get("new_label"),
                r.get("confidence_level"),
                r.get("decision_reason"),
                r.get("error_type"),
            ),
        )
    conn.commit()
    conn.close()


def _insert_annotations(db_path: Path, session_id: str, annotations: list[dict]) -> None:
    """向 comparison_annotations 表插入测试数据。"""
    conn = sqlite3.connect(str(db_path))
    for a in annotations:
        conn.execute(
            """
            INSERT INTO comparison_annotations
                (session_id, entity_key, human_label, reviewer_name, created_at, updated_at)
            VALUES (?, ?, ?, '', '2024-01-01 00:00:00', '2024-01-01 00:00:00')
            """,
            (session_id, a["entity_key"], a["human_label"]),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def engine(tmp_path: Path) -> tuple[ComparisonEngine, Path]:
    """创建测试用 ComparisonEngine 实例。"""
    db_path = _create_test_db(tmp_path)
    config = ComparisonConfig(session_id="test-session", bizdate="20240101")
    engine = ComparisonEngine(sqlite_path=db_path, config=config)
    return engine, db_path


class TestGenerateReport:
    """测试 generate_report 方法。"""

    def test_raises_on_no_annotations(self, engine):
        """无标注时应抛出 ValueError。"""
        eng, db_path = engine
        # 插入差异记录但不标注
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
        ]
        _insert_results(db_path, "s1", records)

        with pytest.raises(ValueError, match="请先完成至少一条记录的标注"):
            eng.generate_report("s1")

    def test_basic_accuracy_calculation(self, engine):
        """基本准确率计算。"""
        eng, db_path = engine
        # 2 条差异记录
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
            {"entity_key": "u2::sc2", "old_label": "B", "new_label": "A"},
        ]
        _insert_results(db_path, "s1", records)

        # 标注：u1 正确答案是 B（new 正确），u2 正确答案是 B（old 正确）
        annotations = [
            {"entity_key": "u1::sc1", "human_label": "B"},
            {"entity_key": "u2::sc2", "human_label": "B"},
        ]
        _insert_annotations(db_path, "s1", annotations)

        report = eng.generate_report("s1")

        # old_accuracy: u1 old=A != human=B, u2 old=B == human=B → 1/2 = 0.5
        assert report["old_accuracy"] == 0.5
        # new_accuracy: u1 new=B == human=B, u2 new=A != human=B → 1/2 = 0.5
        assert report["new_accuracy"] == 0.5
        assert report["improvement"] == 0.0
        assert report["coverage"] == 1.0
        assert report["coverage_warning"] is None

    def test_new_better_than_old(self, engine):
        """新标签全部正确时 improvement > 0。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
            {"entity_key": "u2::sc2", "old_label": "A", "new_label": "C"},
        ]
        _insert_results(db_path, "s1", records)

        # 标注：两条都是 new 正确
        annotations = [
            {"entity_key": "u1::sc1", "human_label": "B"},
            {"entity_key": "u2::sc2", "human_label": "C"},
        ]
        _insert_annotations(db_path, "s1", annotations)

        report = eng.generate_report("s1")

        assert report["old_accuracy"] == 0.0
        assert report["new_accuracy"] == 1.0
        assert report["improvement"] == 1.0

    def test_coverage_warning_when_partial(self, engine):
        """部分标注时应有覆盖率警告。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
            {"entity_key": "u2::sc2", "old_label": "A", "new_label": "C"},
        ]
        _insert_results(db_path, "s1", records)

        # 只标注 1 条
        annotations = [
            {"entity_key": "u1::sc1", "human_label": "B"},
        ]
        _insert_annotations(db_path, "s1", annotations)

        report = eng.generate_report("s1")

        assert report["coverage"] == 0.5
        assert report["coverage_warning"] is not None

    def test_confusion_matrices(self, engine):
        """混淆矩阵正确构建。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
            {"entity_key": "u2::sc2", "old_label": "B", "new_label": "A"},
        ]
        _insert_results(db_path, "s1", records)

        annotations = [
            {"entity_key": "u1::sc1", "human_label": "B"},
            {"entity_key": "u2::sc2", "human_label": "A"},
        ]
        _insert_annotations(db_path, "s1", annotations)

        report = eng.generate_report("s1")

        # old_confusion: {human_label: {old_label: count}}
        # human=B, old=A → old_confusion["B"]["A"] = 1
        # human=A, old=B → old_confusion["A"]["B"] = 1
        assert report["old_confusion_matrix"]["B"]["A"] == 1
        assert report["old_confusion_matrix"]["A"]["B"] == 1

        # new_confusion: {human_label: {new_label: count}}
        # human=B, new=B → new_confusion["B"]["B"] = 1
        # human=A, new=A → new_confusion["A"]["A"] = 1
        assert report["new_confusion_matrix"]["B"]["B"] == 1
        assert report["new_confusion_matrix"]["A"]["A"] == 1

    def test_recommendations_adopt_new(self, engine):
        """新标签更好时建议 adopt_new。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
            {"entity_key": "u2::sc2", "old_label": "A", "new_label": "B"},
        ]
        _insert_results(db_path, "s1", records)

        # 两条都是 new 正确（human=B）
        annotations = [
            {"entity_key": "u1::sc1", "human_label": "B"},
            {"entity_key": "u2::sc2", "human_label": "B"},
        ]
        _insert_annotations(db_path, "s1", annotations)

        report = eng.generate_report("s1")

        # 对于标签 B: human==B 有 2 条，old==B 有 0 条 → old_acc=0, new==B 有 2 条 → new_acc=1
        b_rec = next(r for r in report["recommendations"] if r["label"] == "B")
        assert b_rec["recommendation"] == "adopt_new"

    def test_consistent_records_excluded(self, engine):
        """一致记录（old==new）不参与报告计算。"""
        eng, db_path = engine
        # 1 条一致记录 + 1 条差异记录
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "A"},  # 一致
            {"entity_key": "u2::sc2", "old_label": "A", "new_label": "B"},  # 差异
        ]
        _insert_results(db_path, "s1", records)

        # 两条都标注（一致记录自动标注为 A，差异记录人工标注为 B）
        annotations = [
            {"entity_key": "u1::sc1", "human_label": "A"},
            {"entity_key": "u2::sc2", "human_label": "B"},
        ]
        _insert_annotations(db_path, "s1", annotations)

        report = eng.generate_report("s1")

        # 2 条记录都被标注
        # old_accuracy: u1 old=A human=A ✓, u2 old=A human=B ✗ → 1/2 = 0.5
        # new_accuracy: u1 new=A human=A ✓, u2 new=B human=B ✓ → 2/2 = 1.0
        assert report["new_accuracy"] == 1.0
        assert report["old_accuracy"] == 0.5
        assert report["coverage"] == 1.0  # 2 annotated / 2 total

    def test_report_schema_keys(self, engine):
        """报告包含所有必需的键。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
        ]
        _insert_results(db_path, "s1", records)
        _insert_annotations(db_path, "s1", [{"entity_key": "u1::sc1", "human_label": "B"}])

        report = eng.generate_report("s1")

        expected_keys = {
            "session_id", "old_accuracy", "new_accuracy", "improvement",
            "coverage", "coverage_warning", "label_metrics",
            "old_confusion_matrix", "new_confusion_matrix", "recommendations",
        }
        assert set(report.keys()) == expected_keys
        assert report["session_id"] == "s1"
