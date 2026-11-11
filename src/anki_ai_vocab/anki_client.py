"""AnkiConnect v6 operations. Reads and write plans are separate."""

import html
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import httpx

from .config import Settings
from .errors import AnkiError
from .vocabulary import Vocabulary, clean_tag, normalize, topic_tag

logger = logging.getLogger(__name__)

MODEL_FIELDS = {
    "word": "Word",
    "meaning": "Meaning",
    "example": "Example",
    "example_translation": "ExampleTranslation",
    "part_of_speech": "PartOfSpeech",
    "topic": "Topic",
    "source_sentence": "SourceSentence",
}
ALIASES = {
    "word": ("Word", "Expression", "Term", "单词"),
    "meaning": ("Meaning", "Definition", "Definitions", "释义"),
    "example": ("Example", "Sentence", "例句"),
    "example_translation": (
        "ExampleTranslation",
        "SentenceTranslation",
        "Translation",
        "例句翻译",
    ),
    "part_of_speech": ("PartOfSpeech", "POS", "词性"),
    "topic": ("Topic", "Domain", "领域"),
    "source_sentence": ("SourceSentence",),
}
FRONT = '<div class="word">{{Word}}</div>'
BACK = """{{FrontSide}}<hr id="answer">
<div class="meta">{{PartOfSpeech}} · {{Topic}}</div>
<section><div class="label">中文释义</div>{{Meaning}}</section>
<section><div class="label">英文例句</div>{{Example}}</section>
<section><div class="label">例句翻译</div>{{ExampleTranslation}}</section>"""
CSS = """.card { font-family: sans-serif; font-size: 20px; text-align: left;
color: #202124; background: #fff; line-height: 1.65; padding: 16px;
max-width: 680px; margin: auto; overflow-wrap: anywhere; }
.word { font-size: 32px; font-weight: 700; text-align: center; }
.meta, .label { color: #666; font-size: 15px; }
section { margin-top: 16px; } hr { border: 0; border-top: 1px solid #ccc; }
.nightMode.card, .night_mode.card { color: #eee; background: #202124; }
.nightMode .meta, .nightMode .label, .night_mode .meta, .night_mode .label
{ color: #bbb; }"""


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("br", "div", "p"):
            self.parts.append(" ")


def plain_text(value: str) -> str:
    parser = _PlainText()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())


def safe_html(value: str) -> str:
    return html.escape(value, quote=True).replace("\n", "<br>")


def field_mapping(names: list[str]) -> dict[str, str]:
    by_lower = {name.casefold(): name for name in names}
    return {
        key: next(by_lower[a.casefold()] for a in aliases if a.casefold() in by_lower)
        for key, aliases in ALIASES.items()
        if any(a.casefold() in by_lower for a in aliases)
    }


@dataclass(frozen=True)
class ModelPlan:
    name: str
    mapping: dict[str, str]
    create: bool = False


@dataclass(frozen=True)
class ExistingNote:
    note_id: int
    model: str
    fields: dict[str, Any]
    tags: tuple[str, ...]

    def topic_status(self, topic: str) -> str:
        mapping = field_mapping(list(self.fields))
        if "topic" in mapping:
            value = plain_text(self.fields[mapping["topic"]]["value"])
            if value:
                return "same" if normalize(value) == normalize(topic) else "other"
        identities = [tag for tag in self.tags if tag.startswith("ai_vocab::topic::")]
        if identities:
            return "same" if topic_tag(topic) in identities else "other"
        return "unknown"


def note_fields(entry: Vocabulary, plan: ModelPlan) -> dict[str, str]:
    values = {key: safe_html(getattr(entry, key)) for key in MODEL_FIELDS}
    # A four-field vocabulary model can display all content via Definition.
    extras = [
        ("part_of_speech", "词性"),
        ("topic", "领域"),
    ]
    for key, label in extras:
        if key not in plan.mapping:
            values["meaning"] += f"<br><br><b>{label}</b><br>{values[key]}"
    return {target: values[key] for key, target in plan.mapping.items()}


def note_tags(entry: Vocabulary) -> list[str]:
    return sorted(
        {
            "anki_ai_vocab",
            topic_tag(entry.topic),
            f"topic::{clean_tag(entry.topic)}",
            *entry.tags,
        }
    )


class AnkiClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        # Local Anki traffic must not be routed through HTTP(S)_PROXY.
        self.client = client or httpx.Client(
            timeout=settings.anki_timeout,
            trust_env=False,
        )

    def __enter__(self) -> "AnkiClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.client.close()

    def invoke(self, action: str, **params: Any) -> Any:
        payload: dict[str, Any] = {"action": action, "version": 6, "params": params}
        if self.settings.anki_key:
            payload["key"] = self.settings.anki_key
        try:
            response = self.client.post(self.settings.anki_url, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise AnkiError(
                f"AnkiConnect {action} 超时。"
                "若为写入，请先在 Anki 浏览器检查结果再重试。"
            ) from exc
        except httpx.HTTPError as exc:
            raise AnkiError(
                "无法连接 AnkiConnect，请打开 Anki、检查插件及本机 8765 端口。"
            ) from exc
        except ValueError as exc:
            raise AnkiError("AnkiConnect 返回的内容不是 JSON。") from exc
        if not isinstance(data, dict) or "result" not in data or "error" not in data:
            raise AnkiError("AnkiConnect 响应格式不正确。")
        if data["error"]:
            # Do not echo untrusted server messages or potentially secret fields.
            logger.warning("AnkiConnect 操作失败：%s", action)
            raise AnkiError(
                f"AnkiConnect {action} 失败，"
                "请检查 API Key、牌组、笔记字段及 Anki 界面状态。"
            )
        return data["result"]

    def check(self) -> list[str]:
        version = self.invoke("version")
        if not isinstance(version, int) or version < 6:
            raise AnkiError("需要支持 API v6 的 AnkiConnect。")
        decks = self.invoke("deckNames")
        if self.settings.deck not in decks:
            raise AnkiError(
                f"牌组“{self.settings.deck}”不存在，请在 Anki 创建它或修改 deck 配置。"
            )
        return self.invoke("modelNames")

    def inspect_model(self, name: str) -> ModelPlan | None:
        names = self.invoke("modelFieldNames", modelName=name)
        mapping = field_mapping(names)
        required = {"word", "meaning", "example", "example_translation"}
        if not required <= mapping.keys():
            return None
        templates = self.invoke("modelTemplates", modelName=name)
        # Reuse only a simple word-front, answer-back type. No template changes.
        if len(templates) != 1:
            return None
        template = next(iter(templates.values()))
        front = template.get("Front", "")
        back = template.get("Back", "")
        front_fields = re.findall(r"{{\s*([^{}]+?)\s*}}", front)
        if front_fields != [mapping["word"]]:
            return None
        back_fields = set(re.findall(r"{{\s*([^{}]+?)\s*}}", back))
        # Old templates would leave an empty explanation section on new cards.
        legacy_fields = {"domainexplanation", "professionalexplanation", "专业解释"}
        if any(
            field.lstrip("#^/").split(":")[-1].strip().casefold() in legacy_fields
            for field in back_fields
        ):
            return None
        if not {mapping[k] for k in required - {"word"}} <= back_fields:
            return None
        # Optional fields hidden by a template are bundled into Definition.
        mapping = {
            key: target
            for key, target in mapping.items()
            if key in required or key == "source_sentence" or target in back_fields
        }
        return ModelPlan(name, mapping)

    def plan_model(self, models: list[str]) -> ModelPlan:
        if self.settings.preferred_model in models:
            plan = self.inspect_model(self.settings.preferred_model)
            if plan:
                return plan
        index = 1
        while True:
            name = "AI Vocabulary" if index == 1 else f"AI Vocabulary {index}"
            if name not in models:
                return ModelPlan(name, dict(MODEL_FIELDS), create=True)
            plan = self.inspect_model(name)
            if plan:
                return plan
            index += 1

    def ensure_model(self, plan: ModelPlan) -> None:
        if not plan.create:
            return
        # Called only after confirmation. A concurrent creator is not overwritten.
        if plan.name in self.invoke("modelNames"):
            raise AnkiError("笔记类型列表刚发生变化，请重新运行并预览。")
        self.invoke(
            "createModel",
            modelName=plan.name,
            inOrderFields=list(MODEL_FIELDS.values()),
            css=CSS,
            isCloze=False,
            cardTemplates=[{"Name": "Vocabulary", "Front": FRONT, "Back": BACK}],
        )

    def find_duplicates(self, word: str) -> list[ExistingNote]:
        escaped = word.replace("\\", "\\\\").replace('"', '\\"')
        ids = self.invoke("findNotes", query=f'"{escaped}"')
        matches = []
        for offset in range(0, len(ids), 200):
            for note in self.invoke("notesInfo", notes=ids[offset : offset + 200]):
                fields = note["fields"]
                mapping = field_mapping(list(fields))
                if "word" in mapping:
                    word_field = fields[mapping["word"]]
                else:
                    word_field = min(fields.values(), key=lambda f: f["order"])
                if normalize(plain_text(word_field["value"])) == normalize(word):
                    matches.append(
                        ExistingNote(
                            note["noteId"],
                            note["modelName"],
                            fields,
                            tuple(note.get("tags", [])),
                        )
                    )
        return matches

    def add(
        self, entry: Vocabulary, plan: ModelPlan, allow_duplicate: bool = False
    ) -> int:
        self.ensure_model(plan)
        result = self.invoke(
            "addNote",
            note={
                "deckName": self.settings.deck,
                "modelName": plan.name,
                "fields": note_fields(entry, plan),
                "tags": note_tags(entry),
                "options": {
                    "allowDuplicate": allow_duplicate,
                    "duplicateScope": "collection",
                },
            },
        )
        if not isinstance(result, int):
            raise AnkiError("AnkiConnect 未返回笔记编号，请在 Anki 中检查后再重试。")
        return result

    def check_save_target(
        self,
        entry: Vocabulary,
        existing: ExistingNote | None = None,
        allow_duplicate: bool = False,
    ) -> None:
        """Recheck immediately before writing, after the user confirmation."""
        latest = self.find_duplicates(entry.word)
        if existing:
            current = next((n for n in latest if n.note_id == existing.note_id), None)
            if current != existing:
                raise AnkiError("目标笔记在预览后发生变化，请重新生成并确认。")
        elif any(n.topic_status(entry.topic) == "same" for n in latest):
            raise AnkiError("预览期间出现了相同领域的卡片，已停止新增。")
        elif latest and not allow_duplicate:
            raise AnkiError("预览期间出现了同名单词，请重新生成并选择处理方式。")

    def update(self, note: ExistingNote, entry: Vocabulary, plan: ModelPlan) -> None:
        # Preserve scheduling, media, other fields, decks, and existing tags.
        self.invoke(
            "updateNoteFields",
            note={
                "id": note.note_id,
                "fields": note_fields(entry, plan),
            },
        )
        try:
            self.invoke(
                "addTags", notes=[note.note_id], tags=" ".join(note_tags(entry))
            )
        except AnkiError as exc:
            raise AnkiError(
                "卡片字段已更新，但标签写入失败；请在 Anki 中检查，不要重复新增。"
            ) from exc
