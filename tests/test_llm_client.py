import json
from types import SimpleNamespace

import pytest

from app.core.exceptions import AnalysisValidationError
from app.infrastructure.llm.deepseek_client import DeepSeekLanguageModel


def test_parse_valid_deepseek_json():
    result = DeepSeekLanguageModel._parse(
        json.dumps(
            {
                "source_suggestion": "学校",
                "category_name": "通知",
                "category_suggestion": None,
                "semantic_score": 4,
                "reason": "需要处理",
                "summary": "需要在周五前确认",
                "discard_reason_summary": None,
                "link_summaries": [
                    {"url": "https://example.com/action", "summary": "提交确认信息的页面"}
                ],
            },
            ensure_ascii=False,
        )
    )

    assert result.semantic_score == 4
    assert result.category_name == "通知"
    assert result.link_summaries[0].summary == "提交确认信息的页面"


def test_parse_rejects_invalid_json():
    with pytest.raises(AnalysisValidationError):
        DeepSeekLanguageModel._parse("not-json")


def test_link_summary_validation_requires_each_safe_link():
    from tests.conftest import make_email

    analysis = DeepSeekLanguageModel._parse(
        json.dumps(
            {
                "source_suggestion": None,
                "category_name": "通知",
                "category_suggestion": None,
                "semantic_score": 3,
                "reason": "有链接",
                "summary": "邮件摘要",
                "discard_reason_summary": None,
                "link_summaries": [],
            },
            ensure_ascii=False,
        )
    )

    with pytest.raises(AnalysisValidationError, match="有效链接"):
        DeepSeekLanguageModel._require_link_summaries(make_email(), analysis)


@pytest.mark.asyncio
async def test_empty_response_is_retried(settings, monkeypatch):
    client = DeepSeekLanguageModel(settings)
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "source_suggestion": None,
                                "category_name": "其他",
                                "category_suggestion": None,
                                "semantic_score": 1,
                                "reason": "无行动要求",
                                "summary": "普通推送",
                                "discard_reason_summary": "群发推送且没有行动要求",
                                "link_summaries": [
                                    {"url": "https://example.com/action", "summary": "处理入口"}
                                ],
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        ),
    ]

    class Completions:
        async def create(self, **kwargs):
            return responses.pop(0)

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    from tests.conftest import make_email

    result = await client.analyze_email(make_email(), ("其他",))

    assert result.discard_reason_summary == "群发推送且没有行动要求"
    assert responses == []


@pytest.mark.asyncio
async def test_invalid_json_response_is_retried(settings):
    client = DeepSeekLanguageModel(settings)
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary":"缺字段"}'))]),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "source_suggestion": "学校",
                                "category_name": "学术",
                                "category_suggestion": None,
                                "semantic_score": 4,
                                "reason": "有明确研究安排",
                                "summary": "研究参与安排通知",
                                "discard_reason_summary": None,
                                "link_summaries": [
                                    {"url": "https://example.com/action", "summary": "处理入口"}
                                ],
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        ),
    ]

    class Completions:
        async def create(self, **kwargs):
            return responses.pop(0)

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    from tests.conftest import make_email

    result = await client.analyze_email(make_email(), ("学术", "其他"))

    assert result.category_name == "学术"
    assert result.semantic_score == 4
    assert responses == []


@pytest.mark.asyncio
async def test_missing_link_summaries_are_filled_without_rejecting_email(settings):
    client = DeepSeekLanguageModel(settings)
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "source_suggestion": None,
                            "category_name": "鍏朵粬",
                            "category_suggestion": None,
                            "semantic_score": 2,
                            "reason": "鏃犳槑纭鍔ㄨ姹?",
                            "summary": "閭欢鍖呭惈涓€涓搷浣滈摼鎺?",
                            "discard_reason_summary": None,
                            "link_summaries": [],
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]
    )

    class Completions:
        async def create(self, **kwargs):
            return response

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

    from tests.conftest import make_email

    email = make_email()
    result = await client.analyze_email(email, ("鍏朵粬",))

    assert result.link_summaries[0].url == "https://example.com/action"
    assert result.link_summaries[0].summary == "example.com"


@pytest.mark.asyncio
async def test_invalid_second_response_uses_degraded_analysis(settings):
    client = DeepSeekLanguageModel(settings)
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="still-not-json"))]),
    ]

    class Completions:
        async def create(self, **kwargs):
            return responses.pop(0)

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

    from tests.conftest import make_email

    email = make_email()
    result = await client.analyze_email(email, ("鍏朵粬",))

    assert result.category_name == "鍏朵粬"
    assert result.summary.startswith(email.subject)
    assert result.semantic_score == 0
    assert result.link_summaries[0].summary == "example.com"


@pytest.mark.asyncio
async def test_second_empty_response_uses_degraded_analysis(settings):
    client = DeepSeekLanguageModel(settings)
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
    ]

    class Completions:
        async def create(self, **kwargs):
            return responses.pop(0)

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

    from tests.conftest import make_email

    email = make_email()
    result = await client.analyze_email(email, ("其他",))

    assert result.category_name == "其他"
    assert result.summary.startswith(email.subject)
    assert result.semantic_score == 0
    assert result.link_summaries[0].summary == "example.com"
    assert responses == []


@pytest.mark.asyncio
async def test_long_body_is_truncated_and_max_tokens_from_settings(settings):
    client = DeepSeekLanguageModel(settings)
    captured = {}

    class Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(
                                {
                                    "source_suggestion": None,
                                    "category_name": "其他",
                                    "category_suggestion": None,
                                    "semantic_score": 1,
                                    "reason": "普通信息",
                                    "summary": "摘要",
                                    "discard_reason_summary": None,
                                    "link_summaries": [],
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                ]
            )

    client.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

    from tests.conftest import make_email

    email = make_email(body="甲" * (settings.llm_body_char_limit + 1000), links=())
    await client.analyze_email(email, ("其他",))

    user_payload = json.loads(captured["messages"][1]["content"])
    suffix = "……（正文过长，已截断）"
    body = user_payload["email"]["body"]
    assert body.endswith(suffix)
    assert len(body) <= settings.llm_body_char_limit + len(suffix)
    assert captured["max_tokens"] == settings.llm_max_tokens


def test_parse_accepts_json_code_fence():
    result = DeepSeekLanguageModel._parse(
        "```json\n"
        + json.dumps(
            {
                "source_suggestion": None,
                "category_name": "通知",
                "category_suggestion": None,
                "semantic_score": 2,
                "reason": "普通通知",
                "summary": "通知摘要",
                "discard_reason_summary": None,
            },
            ensure_ascii=False,
        )
        + "\n```"
    )

    assert result.category_name == "通知"
