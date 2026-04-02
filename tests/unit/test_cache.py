from industry_classification.cache import build_cache_key


def test_cache_key_changes_when_taxonomy_version_changes():
    key_v1 = build_cache_key(
        entity_key="abc",
        input_hash="hash",
        graph_version="v1",
        taxonomy_version="v1",
        prompt_version="v1",
        model_version="m1",
    )
    key_v2 = build_cache_key(
        entity_key="abc",
        input_hash="hash",
        graph_version="v1",
        taxonomy_version="v2",
        prompt_version="v1",
        model_version="m1",
    )
    assert key_v1 != key_v2

