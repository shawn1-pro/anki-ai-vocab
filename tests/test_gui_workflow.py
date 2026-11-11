from dataclasses import replace

import pytest
from test_anki import note_info, transport_client

from anki_ai_vocab import gui_workflow
from anki_ai_vocab.anki_client import (
    BACK,
    FRONT,
    MODEL_FIELDS,
    ExistingNote,
    ModelPlan,
)
from anki_ai_vocab.cache import Cache
from anki_ai_vocab.errors import VocabError
from anki_ai_vocab.gui_workflow import DesktopWorkflow, PreparedCapture, SaveTarget


def prepared_capture(entry, notes=()):
    model = ModelPlan("AI Vocabulary", MODEL_FIELDS)
    return PreparedCapture(
        entry.word,
        entry.topic,
        entry.source_sentence,
        tuple(notes),
        model,
        {
            note.note_id: model
            for note in notes
            if note.topic_status(entry.topic) != "other"
        },
    )


def test_prepare_is_read_only_and_finds_update_candidates(settings, entry, monkeypatch):
    notes = [note_info(entry, 1), note_info(replace(entry, topic="Robotics"), 2)]
    results = {
        "version": 6,
        "deckNames": [settings.deck],
        "modelNames": ["AI Vocabulary"],
        "findNotes": [1, 2],
        "notesInfo": notes,
        "modelFieldNames": list(MODEL_FIELDS.values()),
        "modelTemplates": {"Card": {"Front": FRONT, "Back": BACK}},
    }
    anki, requests = transport_client(settings, lambda p: results[p["action"]])
    monkeypatch.setattr(gui_workflow, "AnkiClient", lambda _: anki)
    prepared = DesktopWorkflow(settings).prepare(entry.word, entry.topic)
    assert len(prepared.notes) == 2
    assert set(prepared.updates) == {1}
    assert not settings.data_dir.exists()
    assert not any(
        p["action"] in ("addNote", "createModel", "updateNoteFields") for p in requests
    )


def test_duplicate_skip_needs_no_api(settings, entry):
    assert (
        DesktopWorkflow(settings).choose_target(prepared_capture(entry), "skip") is None
    )


def test_same_topic_duplicate_cannot_be_added(settings, entry):
    note = ExistingNote(1, "AI Vocabulary", {}, ("ai_vocab::topic::unused",))
    note = replace(note, fields=note_info(entry)["fields"])
    with pytest.raises(VocabError, match="相同领域"):
        DesktopWorkflow(settings).choose_target(prepared_capture(entry, [note]), "new")


def test_update_requires_eligible_selected_note(settings, entry):
    note = ExistingNote(7, "AI Vocabulary", note_info(entry)["fields"], ())
    prepared = prepared_capture(entry, [note])
    workflow = DesktopWorkflow(settings)
    assert workflow.choose_target(prepared, "update", 7).existing == note
    with pytest.raises(VocabError, match="请选择"):
        workflow.choose_target(prepared, "update", 999)


def test_different_topic_explicitly_allows_new(settings, entry):
    fields = note_info(replace(entry, topic="Robotics"))["fields"]
    note = ExistingNote(1, "AI Vocabulary", fields, ())
    target = DesktopWorkflow(settings).choose_target(
        prepared_capture(entry, [note]), "new"
    )
    assert target.allow_duplicate and target.existing is None


def test_save_without_confirmation_never_connects(settings, entry, monkeypatch):
    def unexpected(*args):
        raise AssertionError("Unconfirmed save must not connect to Anki")

    monkeypatch.setattr(gui_workflow, "AnkiClient", unexpected)
    prepared = prepared_capture(entry)
    with pytest.raises(VocabError, match="确认"):
        DesktopWorkflow(settings).save(entry, prepared, SaveTarget(prepared.model))
    assert not settings.data_dir.exists()


def test_changed_identity_cannot_save(settings, entry):
    prepared = prepared_capture(entry)
    with pytest.raises(VocabError, match="输入已变化"):
        DesktopWorkflow(settings).save(
            replace(entry, word="other"),
            prepared,
            SaveTarget(prepared.model),
            confirmed=True,
        )


def test_confirmed_save_uses_existing_anki_format(settings, entry, monkeypatch):
    anki, requests = transport_client(
        settings,
        lambda p: [] if p["action"] == "findNotes" else 345,
    )
    monkeypatch.setattr(gui_workflow, "AnkiClient", lambda _: anki)
    prepared = prepared_capture(entry)
    assert (
        DesktopWorkflow(settings).save(
            entry,
            prepared,
            SaveTarget(prepared.model),
            confirmed=True,
        )
        == 345
    )
    assert [p["action"] for p in requests] == ["findNotes", "addNote"]
    assert requests[-1]["params"]["note"]["fields"]["Example"] == entry.example
    with Cache(settings.data_dir / "vocabulary.sqlite3") as cache:
        assert cache.get(entry.word, entry.topic) == entry


def test_save_rechecks_for_concurrent_duplicate(settings, entry, monkeypatch):
    anki, requests = transport_client(
        settings,
        lambda p: [1] if p["action"] == "findNotes" else [note_info(entry)],
    )
    monkeypatch.setattr(gui_workflow, "AnkiClient", lambda _: anki)
    prepared = prepared_capture(entry)
    with pytest.raises(VocabError, match="停止新增"):
        DesktopWorkflow(settings).save(
            entry, prepared, SaveTarget(prepared.model), confirmed=True
        )
    assert not any(p["action"] == "addNote" for p in requests)
    assert not settings.data_dir.exists()


def test_gui_generation_reuses_cache_without_key(no_key, entry):
    with Cache(no_key.data_dir / "vocabulary.sqlite3") as cache:
        cache.put(entry)
    assert DesktopWorkflow(no_key).generate(prepared_capture(entry)) == entry
