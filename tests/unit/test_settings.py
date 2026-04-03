from pathlib import Path

from industry_classification import settings as settings_module


def test_load_llm_settings_reads_only_env_file(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DASHSCOPE_API_KEY=file-key",
                "LLM_BASE_URL=https://file.example/v1/chat/completions",
                "LLM_MODEL=file-model",
                "LLM_TIMEOUT_SEC=45",
                "LLM_MAX_RETRY=4",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_env_path", env_file)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "process-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://process.example/v1/chat/completions")
    monkeypatch.setenv("LLM_MODEL", "process-model")
    monkeypatch.setenv("LLM_TIMEOUT_SEC", "99")
    monkeypatch.setenv("LLM_MAX_RETRY", "7")
    settings_module._load_env_values.cache_clear()
    settings_module.load_llm_settings.cache_clear()

    loaded = settings_module.load_llm_settings()

    assert loaded.api_key == "file-key"
    assert loaded.base_url == "https://file.example/v1/chat/completions"
    assert loaded.model == "file-model"
    assert loaded.timeout_sec == 45
    assert loaded.max_retry == 4


def test_load_odps_settings_reads_only_env_file(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ODPS_ACCESS_KEY_ID=file-ak",
                "ODPS_ACCESS_KEY_SECRET=file-sk",
                "ODPS_PROJECT=file-project",
                "ODPS_ENDPOINT=https://file-odps.example/api",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_env_path", env_file)
    monkeypatch.setenv("ODPS_ACCESS_KEY_ID", "process-ak")
    monkeypatch.setenv("ODPS_ACCESS_KEY_SECRET", "process-sk")
    monkeypatch.setenv("ODPS_PROJECT", "process-project")
    monkeypatch.setenv("ODPS_ENDPOINT", "https://process-odps.example/api")
    settings_module._load_env_values.cache_clear()
    settings_module.load_odps_settings.cache_clear()

    loaded = settings_module.load_odps_settings()

    assert loaded.access_key_id == "file-ak"
    assert loaded.access_key_secret == "file-sk"
    assert loaded.project == "file-project"
    assert loaded.endpoint == "https://file-odps.example/api"
