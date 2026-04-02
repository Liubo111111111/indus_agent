from industry_classification.settings import load_prompt_asset


def test_prompt_assets_load_system_and_user_templates():
    static_asset = load_prompt_asset("static_profile", version="v1")
    dynamic_asset = load_prompt_asset("dynamic_profile", version="v1")
    final_asset = load_prompt_asset("final_decision", version="v1")

    assert "你是招聘行业识别助手" in static_asset.system_prompt
    assert "{enterprise_name}" in static_asset.user_template
    assert "{top_job_names_json}" in dynamic_asset.user_template
    assert "{static_summary}" in final_asset.user_template

