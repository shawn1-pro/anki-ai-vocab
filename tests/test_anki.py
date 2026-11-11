import json
from dataclasses import replace

import httpx
import pytest

from anki_ai_vocab.anki_client import (
    BACK,
    FRONT,
    MODEL_FIELDS,
    AnkiClient,
    ExistingNote,
    ModelPlan,
    note_fields,
)
from anki_ai_vocab.errors import AnkiError
from anki_ai_vocab.vocabulary import topic_tag


def transport_client(settings, respond):
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, json={"result": respond(payload), "error": None})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AnkiClient(settings, client), requests


def note_info(entry, note_id=1, word=None, tags=None):
    fields = {
        name: {"value": getattr(entry, key), "order": index}
        for index, (key, name) in enumerate(MODEL_FIELDS.items())
    }
    if word is not None:
        fields["Word"]["value"] = word
    return {
        "noteId": note_id,
        "modelName": "AI Vocabulary",
        "fields": fields,
        "tags": tags or [],
    }


def test_add_payload_and_html_escaping(settings, entry):
    anki, requests = transport_client(settings, lambda _: 123)
    entry = replace(entry, meaning='<script>alert("x")</script> & 退化')
    with anki:
        assert anki.add(entry, ModelPlan("AI Vocabulary", MODEL_FIELDS)) == 123
    payload = requests[0]
    assert payload["action"] == "addNote"
    assert payload["version"] == 6
    note = payload["params"]["note"]
    assert note["deckName"] == "专业学习"
    assert note["fields"]["Word"] == "degeneracy"
    assert "<script>" not in note["fields"]["Meaning"]
    assert "&lt;script&gt;" in note["fields"]["Meaning"]
    assert "&amp;" in note["fields"]["Meaning"]
    assert note["options"]["allowDuplicate"] is False
    assert topic_tag("SLAM") in note["tags"]


def test_duplicate_detection_exact_case_and_html(settings, entry):
    notes = [
        note_info(entry, 1, "<b>Degeneracy</b>"),
        note_info(entry, 2, "non-degeneracy"),
        note_info(entry, 3, "unrelated"),
    ]
    anki, requests = transport_client(
        settings,
        lambda p: [1, 2, 3] if p["action"] == "findNotes" else notes,
    )
    with anki:
        found = anki.find_duplicates("degeneracy")
    assert [n.note_id for n in found] == [1]
    assert found[0].topic_status("slam") == "same"
    assert found[0].topic_status("Robotics") == "other"
    assert requests[0]["params"]["query"] == '"degeneracy"'


def test_duplicate_first_field_for_unknown_model(settings, entry):
    info = note_info(entry)
    info["fields"] = {"Front": {"value": "degeneracy", "order": 0}}
    anki, _ = transport_client(
        settings, lambda p: [1] if p["action"] == "findNotes" else [info]
    )
    with anki:
        assert len(anki.find_duplicates("degeneracy")) == 1


def test_unknown_topic_uses_machine_tag():
    note = ExistingNote(1, "vocab", {}, (topic_tag("C++"),))
    assert note.topic_status("C++") == "same"
    assert note.topic_status("C") == "other"
    assert ExistingNote(2, "vocab", {}, ()).topic_status("SLAM") == "unknown"


def test_reuse_compatible_vocabsieve_without_modification(settings, entry):
    def respond(p):
        if p["action"] == "modelFieldNames":
            return ["Word", "Definition", "Sentence", "Translation", "Audio"]
        return {
            "Vocabulary": {
                "Front": "{{Word}}",
                "Back": "{{Definition}}{{Sentence}}{{Translation}}",
            }
        }

    anki, requests = transport_client(settings, respond)
    with anki:
        plan = anki.plan_model(["vocabsieve-notes"])
    assert plan.name == "vocabsieve-notes"
    assert not plan.create
    fields = note_fields(entry, plan)
    assert entry.part_of_speech in fields["Definition"]
    assert "专业解释" not in fields["Definition"]
    assert "Audio" not in fields
    assert all(p["action"] in ("modelFieldNames", "modelTemplates") for p in requests)


def test_incompatible_vocabsieve_gets_independent_model(settings):
    anki, requests = transport_client(settings, lambda _: ["Sentence", "Audio"])
    with anki:
        plan = anki.plan_model(["vocabsieve-notes"])
    assert plan.name == "AI Vocabulary" and plan.create
    assert [p["action"] for p in requests] == ["modelFieldNames"]


def test_incompatible_name_collision_is_not_overwritten(settings):
    anki, _ = transport_client(settings, lambda _: ["Front", "Back"])
    with anki:
        plan = anki.plan_model(["AI Vocabulary"])
    assert plan.name == "AI Vocabulary 2"


@pytest.mark.parametrize(
    "field", ["DomainExplanation", "ProfessionalExplanation", "专业解释"]
)
def test_legacy_explanation_template_gets_separate_model(settings, field):
    def respond(payload):
        if payload["action"] == "modelFieldNames":
            return [*MODEL_FIELDS.values(), field]
        return {"Card": {"Front": FRONT, "Back": BACK + "{{" + field + "}}"}}

    anki, requests = transport_client(settings, respond)
    with anki:
        plan = anki.plan_model(["AI Vocabulary"])
    assert plan.name == "AI Vocabulary 2" and plan.create
    assert all(p["action"] in ("modelFieldNames", "modelTemplates") for p in requests)


def test_reject_sentence_front_even_with_matching_fields(settings):
    def respond(p):
        if p["action"] == "modelFieldNames":
            return list(MODEL_FIELDS.values())
        return {"Card": {"Front": "{{Example}}", "Back": BACK}}

    anki, _ = transport_client(settings, respond)
    with anki:
        assert anki.inspect_model("vocabsieve-notes") is None


def test_create_model_schema(settings, entry):
    anki, requests = transport_client(
        settings, lambda p: [] if p["action"] == "modelNames" else 42
    )
    with anki:
        anki.add(entry, ModelPlan("AI Vocabulary", MODEL_FIELDS, create=True))
    assert [p["action"] for p in requests] == ["modelNames", "createModel", "addNote"]
    params = requests[1]["params"]
    assert params["inOrderFields"][0] == "Word"
    assert params["cardTemplates"][0]["Front"] == FRONT
    assert "DomainExplanation" not in params["inOrderFields"]
    assert "专业解释" not in params["cardTemplates"][0]["Back"]
    assert params["isCloze"] is False


def test_update_preserves_unmapped_fields_and_tags(settings, entry):
    note = ExistingNote(
        99, "vocab", {"Audio": {"value": "[sound:keep.mp3]"}}, ("keep_me",)
    )
    plan = ModelPlan("vocab", {"word": "Word", "meaning": "Definition"})
    anki, requests = transport_client(settings, lambda _: None)
    with anki:
        anki.update(note, entry, plan)
    assert [p["action"] for p in requests] == ["updateNoteFields", "addTags"]
    assert requests[0]["params"]["note"]["id"] == 99
    assert "Audio" not in requests[0]["params"]["note"]["fields"]


def test_missing_deck_is_read_only(settings):
    anki, requests = transport_client(
        settings, lambda p: 6 if p["action"] == "version" else []
    )
    with anki, pytest.raises(AnkiError, match="不存在"):
        anki.check()
    assert [p["action"] for p in requests] == ["version", "deckNames"]


@pytest.mark.parametrize(
    "body", [[], {"result": 1}, {"result": None, "error": "secret"}]
)
def test_bad_anki_response(settings, body):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    )
    with AnkiClient(settings, client) as anki, pytest.raises(AnkiError):
        anki.invoke("version")


def test_timeout_does_not_retry_write(settings):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("mock", request=request)

    with AnkiClient(
        settings, httpx.Client(transport=httpx.MockTransport(handler))
    ) as anki:
        with pytest.raises(AnkiError, match="检查结果"):
            anki.invoke("addNote", note={})
    assert len(calls) == 1
