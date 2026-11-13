"""Learning content validation and stable identities."""

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

from .errors import ValidationError

TEXT_FIELDS = (
    "word",
    "topic",
    "meaning",
    "example",
    "example_translation",
    "part_of_speech",
)


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def validate_word(word: str) -> str:
    word = " ".join(word.split())
    if (
        not word
        or len(word) > 120
        or not re.search(r"[A-Za-z]", word)
        or not re.fullmatch(r"[A-Za-z0-9 +#._()'’/-]+", word)
    ):
        raise ValidationError(
            "请输入 1–120 字符的英文单词或技术术语，不要输入整段文字。"
        )
    return word


def validate_topic(topic: str) -> str:
    topic = " ".join(topic.split())
    if not topic or len(topic) > 80:
        raise ValidationError("专业领域应为 1–80 个字符。")
    return topic


def clean_tag(tag: str) -> str:
    return re.sub(r"[^\w:+#.-]", "_", tag.strip(), flags=re.UNICODE)[:80]


def topic_tag(topic: str) -> str:
    digest = hashlib.sha256(normalize(topic).encode()).hexdigest()[:16]
    return f"ai_vocab::topic::{digest}"


@dataclass(frozen=True)
class Vocabulary:
    word: str
    topic: str
    meaning: str
    example: str
    example_translation: str
    part_of_speech: str
    tags: tuple[str, ...]
    source_sentence: str = ""
    phonetic: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "Vocabulary":
        if not isinstance(data, dict):
            raise ValidationError("模型输出应为 JSON 对象。")
        for name in TEXT_FIELDS:
            value = data.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"学习内容缺少有效字段：{name}")
            if len(value) > 8000:
                raise ValidationError(f"字段 {name} 过长。")
        tags = data.get("tags")
        if (
            not isinstance(tags, (list, tuple))
            or len(tags) > 16
            or not all(isinstance(t, str) and t.strip() and len(t) <= 80 for t in tags)
        ):
            raise ValidationError("tags 必须是最多 16 个非空字符串组成的数组。")
        source = data.get("source_sentence", "")
        if not isinstance(source, str) or len(source) > 8000:
            raise ValidationError("原句必须是最多 8000 个字符的字符串。")
        # Older cache entries have no pronunciation; keep them usable offline.
        phonetic = data.get("phonetic", "")
        if not isinstance(phonetic, str) or len(phonetic) > 1000:
            raise ValidationError("音标必须是最多 1000 个字符的字符串。")
        return cls(
            **{name: data[name].strip() for name in TEXT_FIELDS},
            tags=tuple(dict.fromkeys(clean_tag(t) for t in tags if clean_tag(t))),
            source_sentence=source,
            phonetic=phonetic.strip(),
        )


def parse_vocabulary(raw: str) -> Vocabulary:
    raw = raw.strip()
    # Some compatible models still wrap JSON in a Markdown fence.
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw, count=1, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw, count=1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "模型未返回有效 JSON；可手动重新生成，不会自动重复付费。"
        ) from exc
    return Vocabulary.from_dict(data)
