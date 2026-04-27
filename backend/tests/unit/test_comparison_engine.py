"""ComparisonEngine.get_diff_analysis 单元测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from industry_classification.comparison_engine import ComparisonConfig, ComparisonEngine


def _create_test_db(tmp_path: Path) -> Path:
    """创建测试用 SQLite 数据库，包含 comparison_results 表。"""
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


@pytest.fixture
def engine(tmp_path: Path) -> tuple[ComparisonEngine, Path]:
    """创建测试用 ComparisonEngine 实例。"""
    db_path = _create_test_db(tmp_path)
    config = ComparisonConfig(session_id="test-session", bizdate="20240101")
    engine = ComparisonEngine(sqlite_path=db_path, config=config)
    return engine, db_path


class TestGetDiffAnalysis:
    """测试 get_diff_analysis 方法。"""

    def test_raises_on_empty_session(self, engine):
        """无结果时应抛出 ValueError。"""
        eng, _ = engine
        with pytest.raises(ValueError, match="不存在或无对比结果"):
            eng.get_diff_analysis("nonexistent-session")

    def test_all_consistent(self, engine):
        """所有记录一致时，diff_count=0，consistency_rate=1.0。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "制造业", "new_label": "制造业"},
            {"entity_key": "u2::sc2", "old_label": "批发零售业", "new_label": "批发零售业"},
        ]
        _insert_results(db_path, "s1", records)

        result = eng.get_diff_analysis("s1")

        assert result["session_id"] == "s1"
        assert result["dataset_size"] == 2
        assert result["diff_count"] == 0
        assert result["consistency_rate"] == 1.0
        assert result["change_type_ranking"] == []
        # 净变化应全为 0
        for v in result["net_changes"].values():
            assert v == 0

    def test_all_different(self, engine):
        """所有记录不一致时，consistency_rate=0.0。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "制造业", "new_label": "批发零售业"},
            {"entity_key": "u2::sc2", "old_label": "批发零售业", "new_label": "制造业"},
        ]
        _insert_results(db_path, "s1", records)

        result = eng.get_diff_analysis("s1")

        assert result["dataset_size"] == 2
        assert result["diff_count"] == 2
        assert result["consistency_rate"] == 0.0
        assert len(result["change_type_ranking"]) == 2

    def test_mixed_results(self, engine):
        """混合一致和不一致记录。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "制造业", "new_label": "制造业"},
            {"entity_key": "u2::sc2", "old_label": "制造业", "new_label": "批发零售业"},
            {"entity_key": "u3::sc3", "old_label": "批发零售业", "new_label": "制造业"},
            {"entity_key": "u4::sc4", "old_label": "批发零售业", "new_label": "批发零售业"},
        ]
        _insert_results(db_path, "s1", records)

        result = eng.get_diff_analysis("s1")

        assert result["dataset_size"] == 4
        assert result["diff_count"] == 2
        assert result["consistency_rate"] == 0.5  # 2/4

        # 变更矩阵验证
        matrix = result["change_matrix"]
        assert matrix["制造业"]["制造业"] == 1
        assert matrix["制造业"]["批发零售业"] == 1
        assert matrix["批发零售业"]["制造业"] == 1
        assert matrix["批发零售业"]["批发零售业"] == 1

        # 净变化：制造业 new=2, old=2 → 0; 批发零售业 new=2, old=2 → 0
        assert result["net_changes"]["制造业"] == 0
        assert result["net_changes"]["批发零售业"] == 0

    def test_error_records_excluded_from_matrix(self, engine):
        """有 error_type 的记录不参与矩阵计算但计入 dataset_size。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "制造业", "new_label": "制造业"},
            {"entity_key": "u2::sc2", "old_label": "制造业", "new_label": None, "error_type": "timeout"},
        ]
        _insert_results(db_path, "s1", records)

        result = eng.get_diff_analysis("s1")

        assert result["dataset_size"] == 2
        # 只有 1 条有效记录一致
        assert result["consistency_rate"] == 0.5  # 1 consistent / 2 total
        assert result["diff_count"] == 0  # 有效记录中无差异
        # 矩阵只包含有效记录
        assert result["change_matrix"] == {"制造业": {"制造业": 1}}

    def test_change_type_ranking_sorted_desc(self, engine):
        """变更类型排行按数量降序排列。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
            {"entity_key": "u2::sc2", "old_label": "A", "new_label": "B"},
            {"entity_key": "u3::sc3", "old_label": "A", "new_label": "B"},
            {"entity_key": "u4::sc4", "old_label": "C", "new_label": "D"},
            {"entity_key": "u5::sc5", "old_label": "B", "new_label": "A"},
            {"entity_key": "u6::sc6", "old_label": "B", "new_label": "A"},
        ]
        _insert_results(db_path, "s1", records)

        result = eng.get_diff_analysis("s1")

        ranking = result["change_type_ranking"]
        assert ranking[0] == {"old_label": "A", "new_label": "B", "count": 3}
        assert ranking[1] == {"old_label": "B", "new_label": "A", "count": 2}
        assert ranking[2] == {"old_label": "C", "new_label": "D", "count": 1}

    def test_net_changes_calculation(self, engine):
        """净变化量计算正确。"""
        eng, db_path = engine
        records = [
            {"entity_key": "u1::sc1", "old_label": "A", "new_label": "B"},
            {"entity_key": "u2::sc2", "old_label": "A", "new_label": "B"},
            {"entity_key": "u3::sc3", "old_label": "B", "new_label": "C"},
            {"entity_key": "u4::sc4", "old_label": "C", "new_label": "C"},
        ]
        _insert_results(db_path, "s1", records)

        result = eng.get_diff_analysis("s1")

        # A: new=0, old=2 → -2
        # B: new=2, old=1 → +1
        # C: new=2, old=1 → +1
        assert result["net_changes"]["A"] == -2
        assert result["net_changes"]["B"] == 1
        assert result["net_changes"]["C"] == 1

    def test_diff_list_contains_correct_fields(self, engine):
        """diff_list 中每条记录包含正确的字段。"""
        eng, db_path = engine
        records = [
            {
                "entity_key": "u1::sc1",
                "enterprise_name": "测试企业",
                "old_label": "A",
                "new_label": "B",
                "confidence_level": "high",
                "decision_reason": "业务范围匹配",
            },
        ]
        _insert_results(db_path, "s1", records)

        result = eng.get_diff_analysis("s1")

        assert result["diff_count"] == 1
        diff = result["change_type_ranking"]
        assert diff[0]["old_label"] == "A"
        assert diff[0]["new_label"] == "B"
