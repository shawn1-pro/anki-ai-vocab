import json

import httpx
import pytest
from openai import OpenAI

from anki_ai_vocab.cache import Cache
from anki_ai_vocab.deepseek_client import DeepSeekClient
from anki_ai_vocab.errors import GenerationError, ValidationError


def completion(entry, **changes):
    result = {
        "id": "mock_completion",
        "created": 1,
        "object": "chat.completion",
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(entry.to_dict()),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 70,
            "total_tokens": 170,
            "prompt_cache_hit_tokens": 20,
        },
    }
    result.update(changes)
    return result


def sdk(handler):
    return OpenAI(
        api_key="test_key",
        base_url="https://api.deepseek.com",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )


def test_actual_sdk_json_payload_and_usage(settings, entry):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion(entry))

    with Cache(settings.data_dir / "cache.sqlite3") as cache:
        client = DeepSeekClient(settings, cache, sdk(handler))
        assert client.generate(entry.word, entry.topic) == entry
        client.close()
        assert cache.usage()[0]["total_tokens"] == 170
        assert cache.usage()[0]["cached_tokens"] == 20
    payload = requests[0]
    assert payload["model"] == "deepseek-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 1000
    assert "tools" not in payload
    system_prompt = payload["messages"][0]["content"]
    assert "domain_explanation" not in system_prompt
    assert "简短词义或短语" in system_prompt
    assert "phonetic" in system_prompt
    assert "国际音标（IPA）" in system_prompt
    assert len(requests) == 1


@pytest.mark.parametrize(
    "status,hint",
    [
        (401, "认证失败"),
        (429, "429"),
        (500, "500"),
        (400, "模型名"),
        (402, "余额"),
    ],
)
def test_http_errors_no_retries_or_secret_output(settings, status, hint):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "secret_server_body"}})

    with Cache(settings.data_dir / "cache.sqlite3") as cache:
        client = DeepSeekClient(settings, cache, sdk(handler))
        with pytest.raises(GenerationError, match=hint) as caught:
            client.generate("degeneracy", "SLAM")
        client.close()
        assert "secret_server_body" not in str(caught.value)
        assert cache.usage() == []
    assert len(requests) == 1


@pytest.mark.parametrize(
    "error,hint",
    [
        (httpx.ReadTimeout, "超时"),
        (httpx.ConnectError, "网络"),
    ],
)
def test_network_failures(settings, error, hint):
    def handler(request):
        raise error("mock failure", request=request)

    with Cache(settings.data_dir / "cache.sqlite3") as cache:
        client = DeepSeekClient(settings, cache, sdk(handler))
        with pytest.raises(GenerationError, match=hint):
            client.generate("degeneracy", "SLAM")
        client.close()


@pytest.mark.parametrize(
    "variant",
    [
        "json",
        "length",
        "word",
        "context",
        "blank",
        "missing_phonetic",
        "blank_phonetic",
    ],
)
def test_bad_completion_still_records_billed_tokens(settings, entry, variant):
    data = completion(entry)
    choice = data["choices"][0]
    if variant == "json":
        choice["message"]["content"] = "not json"
    elif variant == "blank":
        choice["message"]["content"] = " "
    elif variant == "length":
        choice["finish_reason"] = "length"
    elif variant == "word":
        content = entry.to_dict()
        content["word"] = "other"
        choice["message"]["content"] = json.dumps(content)
    elif variant in ("missing_phonetic", "blank_phonetic"):
        content = entry.to_dict()
        if variant == "missing_phonetic":
            del content["phonetic"]
        else:
            content["phonetic"] = "  "
        choice["message"]["content"] = json.dumps(content)
    with Cache(settings.data_dir / "cache.sqlite3") as cache:
        client = DeepSeekClient(
            settings, cache, sdk(lambda _: httpx.Response(200, json=data))
        )
        with pytest.raises(ValidationError):
            client.generate(
                entry.word,
                entry.topic,
                "Original sentence." if variant == "context" else "",
            )
        assert cache.usage()[0]["requests"] == 1
        client.close()


def test_no_key_fails_before_network(no_key):
    with Cache(no_key.data_dir / "cache.sqlite3") as cache:
        with pytest.raises(GenerationError, match="DEEPSEEK_API_KEY"):
            DeepSeekClient(no_key, cache)
