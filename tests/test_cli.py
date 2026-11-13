import json
from dataclasses import replace

import httpx
import pytest
from test_anki import note_info

from anki_ai_vocab import cli, service
from anki_ai_vocab.anki_client import BACK, FRONT, MODEL_FIELDS, AnkiClient
from anki_ai_vocab.cache import Cache
from anki_ai_vocab.errors import GenerationError

WRITES = {"addNote", "createModel", "updateNoteFields", "addTags"}


@pytest.fixture
def cli_run(settings, entry, monkeypatch):
    def run(
        answers,
        notes=None,
        new_model=False,
        fail_generation=False,
        argv=None,
        changed=False,
    ):
        calls = []
        remote_calls = []
        confirmed = []
        answers_iter = iter(answers)
        searches = []

        def ask(prompt):
            answer = next(answers_iter)
            if "确认保存" in prompt and answer == "s":
                confirmed.append(True)
            return answer

        def handler(request):
            payload = json.loads(request.content)
            calls.append(payload)
            action = payload["action"]
            if action in WRITES:
                assert confirmed, f"Write occurred without confirmation: {action}"
            if action == "findNotes":
                searches.append(1)
            current_notes = notes or []
            if changed and len(searches) > 1:
                current_notes = [note_info(entry, 999)]
            result = {
                "version": 6,
                "deckNames": [settings.deck],
                "modelNames": [] if new_model else ["AI Vocabulary"],
                "modelFieldNames": list(MODEL_FIELDS.values()),
                "modelTemplates": {"Card": {"Front": FRONT, "Back": BACK}},
                "findNotes": [n["noteId"] for n in current_notes],
                "notesInfo": current_notes,
                "addNote": 555,
                "updateNoteFields": None,
                "addTags": None,
                "createModel": {},
            }[action]
            return httpx.Response(200, json={"result": result, "error": None})

        class FakeDeepSeek:
            def __init__(self, *args):
                pass

            def generate(self, word, topic, context):
                remote_calls.append((word, topic, context))
                if fail_generation:
                    raise GenerationError("mock generation failure")
                return replace(
                    entry,
                    word=word,
                    topic=topic,
                    source_sentence=context,
                    example=context or entry.example,
                )

            def close(self):
                pass

        monkeypatch.setattr(cli, "load_settings", lambda *args: settings)
        monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", ask)
        monkeypatch.setattr(service, "DeepSeekClient", FakeDeepSeek)
        monkeypatch.setattr(
            cli,
            "AnkiClient",
            lambda s: AnkiClient(
                s,
                httpx.Client(transport=httpx.MockTransport(handler)),
            ),
        )
        status = cli.main(argv or ["add", "degeneracy", "--topic", "SLAM"])
        return status, calls, remote_calls

    return run


def test_cancel_does_not_create_model_or_note(cli_run):
    status, calls, remote = cli_run(["c"], new_model=True)
    assert status == 0 and len(remote) == 1
    assert not any(p["action"] in WRITES for p in calls)


def test_confirm_creates_type_and_note_only_after_preview(cli_run):
    status, calls, _ = cli_run(["s"], new_model=True)
    assert status == 0
    assert [p["action"] for p in calls if p["action"] in WRITES] == [
        "createModel",
        "addNote",
    ]


def test_duplicate_default_skips_before_api_or_cache(cli_run, settings, entry):
    status, calls, remote = cli_run([""], notes=[note_info(entry)])
    assert status == 0
    assert not remote
    assert not settings.data_dir.exists()
    assert not any(p["action"] in WRITES for p in calls)


def test_same_topic_new_is_rejected(cli_run, entry):
    status, calls, remote = cli_run(["n", "s"], notes=[note_info(entry)])
    assert status == 0 and not remote
    assert not any(p["action"] in WRITES for p in calls)


def test_different_topic_can_add_after_confirmation(cli_run, entry):
    status, calls, _ = cli_run(
        ["n", "s"], notes=[note_info(replace(entry, topic="Robotics"))]
    )
    assert status == 0
    note = next(p for p in calls if p["action"] == "addNote")["params"]["note"]
    assert note["options"]["allowDuplicate"] is True


def test_update_selected_note_after_confirmation(cli_run, entry):
    status, calls, _ = cli_run(["u", "1", "s"], notes=[note_info(entry, 78)])
    assert status == 0
    writes = [p for p in calls if p["action"] in WRITES]
    assert [p["action"] for p in writes] == ["updateNoteFields", "addTags"]
    assert writes[0]["params"]["note"]["id"] == 78


def test_edit_then_save(cli_run):
    status, calls, _ = cli_run(["e", "1", "我修改的释义", "s"])
    assert status == 0
    note = next(p for p in calls if p["action"] == "addNote")["params"]["note"]
    assert note["fields"]["Meaning"] == "我修改的释义"


def test_edit_phonetic_then_save(cli_run):
    edited = "/ˈtest/"
    number = str(cli.EDITABLE.index("phonetic") + 1)
    status, calls, _ = cli_run(["e", number, edited, "s"])
    assert status == 0
    note = next(p for p in calls if p["action"] == "addNote")["params"]["note"]
    assert note["fields"]["Phonetic"] == edited


def test_regenerate_is_explicit(cli_run):
    status, _, remote = cli_run(["r", "c"])
    assert status == 0 and len(remote) == 2


def test_concurrent_duplicate_blocks_save(cli_run):
    status, calls, _ = cli_run(["s"], changed=True)
    assert status == 1
    assert not any(p["action"] in WRITES for p in calls)


def test_generation_error_no_writes(cli_run):
    status, calls, _ = cli_run([], fail_generation=True)
    assert status == 1
    assert not any(p["action"] in WRITES for p in calls)


@pytest.mark.parametrize("has_phonetic", [True, False])
def test_cached_preview_without_key_or_anki(
    settings, entry, monkeypatch, capsys, has_phonetic
):
    monkeypatch.setattr(
        cli, "load_settings", lambda *args: replace(settings, api_key="")
    )
    with Cache(settings.data_dir / "vocabulary.sqlite3") as cache:
        legacy = {**entry.to_dict(), "domain_explanation": "旧版冗长的解释"}
        if not has_phonetic:
            del legacy["phonetic"]
        cache.db.execute(
            "INSERT INTO vocabulary(word, topic, context, content) VALUES(?,?,?,?)",
            (entry.word, "slam", "", json.dumps(legacy)),
        )
        cache.db.commit()
    assert cli.main(["add", "degeneracy", "--topic", "SLAM", "--preview-only"]) == 0
    output = capsys.readouterr().out
    assert "退化" in output
    assert entry.example in output
    assert "音标（IPA）" in output
    assert (entry.phonetic if has_phonetic else "重新生成补齐") in output
    assert "专业解释" not in output
    assert "旧版冗长的解释" not in output


def test_edit_menu_moves_example_up_after_removing_explanation(
    entry, monkeypatch, capsys
):
    example = "Degeneracy can reduce estimation accuracy."
    answers = iter(["2", example])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    edited = cli.edit_entry(entry)
    assert edited.example == example
    assert "专业解释" not in capsys.readouterr().out


def test_noninteractive_save_rejected(settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda *args: settings)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    assert cli.main(["add", "degeneracy"]) == 1
    assert "交互式终端" in capsys.readouterr().err


def test_usage_without_history_does_not_create_database(settings, monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda *args: settings)
    assert cli.main(["usage"]) == 0
    assert not settings.data_dir.exists()
