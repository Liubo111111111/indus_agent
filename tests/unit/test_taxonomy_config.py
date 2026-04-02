from industry_classification.settings import load_taxonomy


def test_taxonomy_contains_all_11_labels_once():
    taxonomy = load_taxonomy()
    names = [label.display_name for label in taxonomy.labels]
    assert len(names) == 11
    assert names.count("其他") == 1

