"""Desktop operations without Tk dependencies or cross-thread resources."""

from dataclasses import dataclass

from .anki_client import AnkiClient, ExistingNote, ModelPlan
from .cache import Cache
from .config import Settings
from .errors import VocabError
from .service import VocabularyService
from .vocabulary import Vocabulary, normalize, validate_topic, validate_word


@dataclass(frozen=True)
class PreparedCapture:
    word: str
    topic: str
    context: str
    notes: tuple[ExistingNote, ...]
    model: ModelPlan
    updates: dict[int, ModelPlan]


@dataclass(frozen=True)
class SaveTarget:
    model: ModelPlan
    existing: ExistingNote | None = None
    allow_duplicate: bool = False


class DesktopWorkflow:
    def __init__(self, settings: Settings):
        self.settings = settings

    def prepare(self, word: str, topic: str, context: str = "") -> PreparedCapture:
        word, topic, context = (
            validate_word(word),
            validate_topic(topic),
            context.strip(),
        )
        if len(context) > 8000:
            raise VocabError("原句最多 8000 字符。")
        with AnkiClient(self.settings) as anki:
            models = anki.check()
            notes = tuple(anki.find_duplicates(word))
            updates = {}
            for note in notes:
                if note.topic_status(topic) != "other":
                    plan = anki.inspect_model(note.model)
                    if plan:
                        updates[note.note_id] = plan
            model = anki.plan_model(models)
        return PreparedCapture(word, topic, context, notes, model, updates)

    def choose_target(
        self,
        prepared: PreparedCapture,
        action: str,
        note_id: int | None = None,
    ) -> SaveTarget | None:
        if action == "skip":
            return None
        if action == "update":
            if note_id not in prepared.updates:
                raise VocabError("请选择可更新且领域一致的笔记。")
            note = next(n for n in prepared.notes if n.note_id == note_id)
            return SaveTarget(prepared.updates[note_id], note)
        if action != "new":
            raise VocabError("请选择跳过、更新或按不同领域新增。")
        if any(n.topic_status(prepared.topic) == "same" for n in prepared.notes):
            raise VocabError("已有相同领域的卡片，请跳过或更新。")
        return SaveTarget(prepared.model, allow_duplicate=bool(prepared.notes))

    def generate(self, prepared: PreparedCapture, force: bool = False) -> Vocabulary:
        with Cache(self.settings.data_dir / "vocabulary.sqlite3") as cache:
            return VocabularyService(self.settings, cache).get(
                prepared.word,
                prepared.topic,
                prepared.context,
                force,
            )

    def save(
        self,
        entry: Vocabulary,
        prepared: PreparedCapture,
        target: SaveTarget,
        *,
        confirmed: bool = False,
    ) -> int:
        if not confirmed:
            raise VocabError("请先预览并确认保存。")
        if (
            normalize(entry.word) != normalize(prepared.word)
            or normalize(entry.topic) != normalize(prepared.topic)
            or entry.source_sentence != prepared.context
        ):
            raise VocabError("输入已变化，请重新生成预览。")
        with AnkiClient(self.settings) as anki:
            anki.check_save_target(entry, target.existing, target.allow_duplicate)
            with Cache(self.settings.data_dir / "vocabulary.sqlite3") as cache:
                cache.put(entry)
            if target.existing:
                anki.update(target.existing, entry, target.model)
                return target.existing.note_id
            return anki.add(entry, target.model, target.allow_duplicate)
