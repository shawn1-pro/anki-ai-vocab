"""Small JSON configuration, with secrets loaded exclusively from env/.env."""

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .errors import VocabError

DEFAULT_TOPICS = (
    "General",
    "SLAM",
    "Computer Vision",
    "C++",
    "Python",
    "Robotics",
    "Mathematics",
    "Control Theory",
)


@dataclass(frozen=True)
class Settings:
    model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    api_timeout: float = 30
    max_tokens: int = 1000
    anki_url: str = "http://127.0.0.1:8765"
    anki_timeout: float = 10
    deck: str = "专业学习"
    preferred_model: str = "vocabsieve-notes"
    default_topic: str = "General"
    topics: tuple[str, ...] = DEFAULT_TOPICS
    data_dir: Path = Path("data")
    api_key: str = field(default="", repr=False)
    anki_key: str = field(default="", repr=False)


def load_settings(
    config_path: Path | None = None,
    env_file: Path | None = None,
) -> Settings:
    explicit = config_path is not None or bool(os.getenv("ANKI_WORD_CONFIG"))
    config_path = (
        Path(config_path or os.getenv("ANKI_WORD_CONFIG", "config.json"))
        .expanduser()
        .resolve()
    )
    base = config_path.parent
    load_dotenv(
        env_file or os.getenv("ANKI_WORD_ENV_FILE") or base / ".env",
        override=False,
    )
    try:
        if explicit and not config_path.is_file():
            raise VocabError(f"配置文件不存在：{config_path}")
        data = json.loads(config_path.read_text()) if config_path.is_file() else {}
        allowed = {f.name for f in fields(Settings)} - {"api_key", "anki_key"}
        if not isinstance(data, dict) or set(data) - allowed:
            raise VocabError(
                "配置必须是 JSON 对象，仅支持 config.example.json 中的选项。"
            )
        for key in ("model", "deck", "preferred_model", "default_topic"):
            if key in data and (
                not isinstance(data[key], str) or not data[key].strip()
            ):
                raise VocabError(f"配置 {key} 必须是非空字符串。")
        for key in ("api_timeout", "anki_timeout"):
            value = data.get(key, 30 if key == "api_timeout" else 10)
            if type(value) not in (float, int) or not 1 <= value <= 300:
                raise VocabError(f"配置 {key} 必须为 1–300 秒。")
        tokens = data.get("max_tokens", 1000)
        if type(tokens) is not int or not 128 <= tokens <= 4096:
            raise VocabError("max_tokens 必须是 128–4096 的整数。")
        topics = data.get("topics", DEFAULT_TOPICS)
        if not isinstance(topics, (list, tuple)) or not all(
            isinstance(t, str) and t.strip() and len(t) <= 80 for t in topics
        ):
            raise VocabError("topics 必须是非空领域名称组成的数组。")
        data["topics"] = tuple(topics)
        # This tool is intended to send vocabulary only to the official API.
        api_url = data.get("deepseek_base_url", Settings.deepseek_base_url)
        if api_url.rstrip("/") not in (
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
        ):
            raise VocabError("deepseek_base_url 仅支持 DeepSeek 官方 HTTPS 地址。")
        anki_url = urlparse(data.get("anki_url", Settings.anki_url))
        if (
            anki_url.scheme != "http"
            or anki_url.hostname not in ("127.0.0.1", "localhost", "::1")
            or anki_url.username
            or anki_url.password
            or anki_url.query
            or anki_url.fragment
        ):
            raise VocabError(
                "anki_url 必须是本机 HTTP 地址，例如 http://127.0.0.1:8765。"
            )
        data_dir = Path(data.get("data_dir", "data")).expanduser()
        data["data_dir"] = (base / data_dir).resolve()
        return Settings(
            **data,
            api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            anki_key=os.getenv("ANKICONNECT_API_KEY", "").strip(),
        )
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise VocabError("配置读取失败，请检查文件路径、JSON 格式和选项类型。") from exc
