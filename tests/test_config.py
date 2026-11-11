import json

import pytest

from anki_ai_vocab.config import load_settings
from anki_ai_vocab.errors import VocabError


def test_defaults_paths_and_env_precedence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment_key")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=file_key\n")
    settings = load_settings()
    assert settings.api_key == "environment_key"
    assert settings.model == "deepseek-flash"
    assert settings.data_dir == tmp_path / "data"
    assert "environment_key" not in repr(settings)


def test_configuration_and_custom_topics(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"model": "deepseek-v4-pro", "topics": ["ROS2"]}))
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=local_test_key\n")
    settings = load_settings(config)
    assert settings.model == "deepseek-v4-pro"
    assert settings.topics == ("ROS2",)
    assert settings.api_key == "local_test_key"


@pytest.mark.parametrize(
    "data",
    [
        {"api_key": "forbidden"},
        {"max_tokens": "1000"},
        {"max_tokens": 999999},
        {"api_timeout": 0},
        {"topics": "SLAM"},
        {"model": ""},
        {"anki_url": "http://remote.example:8765"},
        {"deepseek_base_url": "http://api.deepseek.com"},
        {"deepseek_base_url": "https://other.example"},
        [],
    ],
)
def test_invalid_configuration(tmp_path, data):
    config = tmp_path / "config.json"
    config.write_text(json.dumps(data))
    with pytest.raises(VocabError):
        load_settings(config)


def test_missing_explicit_config(tmp_path):
    with pytest.raises(VocabError, match="不存在"):
        load_settings(tmp_path / "missing.json")
