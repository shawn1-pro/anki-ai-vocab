import json

import pytest

from anki_ai_vocab.errors import ValidationError
from anki_ai_vocab.vocabulary import (
    Vocabulary,
    parse_vocabulary,
    topic_tag,
    validate_word,
)


def test_parse_json_and_fenced_json(entry):
    raw = json.dumps(entry.to_dict(), ensure_ascii=False)
    assert parse_vocabulary(raw) == entry
    assert parse_vocabulary(f"```json\n{raw}\n```") == entry


@pytest.mark.parametrize(
    "field",
    [
        "word",
        "topic",
        "meaning",
        "example",
        "example_translation",
        "part_of_speech",
        "tags",
    ],
)
def test_missing_fields(entry, field):
    data = entry.to_dict()
    del data[field]
    with pytest.raises(ValidationError):
        Vocabulary.from_dict(data)


@pytest.mark.parametrize("raw", ["", " ", "not json", "[]", '{"word":'])
def test_invalid_json(raw):
    with pytest.raises(ValidationError):
        parse_vocabulary(raw)


@pytest.mark.parametrize("tags", ["SLAM", [123], [""], ["x"] * 17])
def test_invalid_tag_shape(entry, tags):
    with pytest.raises(ValidationError):
        Vocabulary.from_dict({**entry.to_dict(), "tags": tags})


@pytest.mark.parametrize("word", ["C++", "C#", "snake_case", "SE(3)", "Kalman filter"])
def test_technical_terms(word):
    assert validate_word(word) == word


@pytest.mark.parametrize("word", ["", "123", 'word" OR tag:*', "中文", "a" * 121])
def test_reject_invalid_words(word):
    with pytest.raises(ValidationError):
        validate_word(word)


def test_topic_identity_handles_symbols():
    assert topic_tag(" C++ ") == topic_tag("c++")
    assert topic_tag("C++") != topic_tag("C")
