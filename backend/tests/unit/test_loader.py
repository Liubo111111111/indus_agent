import json

from industry_classification.loader import load_rows_from_file


def test_load_rows_from_file_reads_jsonl_and_filters_partition(tmp_path):
    rows = [
        {"social_credit_code": "abc", "pt": "20260402"},
        {"social_credit_code": "xyz", "pt": "20260401"},
        {"social_credit_code": "def", "pt": "20260402"},
    ]
    source = tmp_path / "wide_rows.jsonl"
    source.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )

    loaded = list(load_rows_from_file(source, pt="20260402"))

    assert [row["social_credit_code"] for row in loaded] == ["abc", "def"]

