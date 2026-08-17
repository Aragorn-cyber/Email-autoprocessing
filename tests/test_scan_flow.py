import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.enums import ScanStatus
from app.domain.entities import AnalyzedLink, SemanticAnalysis
from app.infrastructure.llm.deepseek_client import DeepSeekLanguageModel
from app.infrastructure.models import (
    ClassificationSuggestionModel,
    EmailAnalysisModel,
    EmailModel,
    LocalReadMailModel,
    ProcessedUidModel,
)
from app.main import create_application
from app.services.report_service import ReportService
from tests.conftest import FakeEmailProvider, FakeLanguageModel, add_account, make_email


@pytest.mark.asyncio
async def test_scan_keeps_email_when_llm_returns_invalid_json_twice(settings, password_env):
    model = DeepSeekLanguageModel(settings)
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="still-not-json"))]),
    ]

    class Completions:
        async def create(self, **kwargs):
            return responses.pop(0)

    model.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    app = create_application(settings, FakeEmailProvider({1: [make_email()]}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)

    assert result.status == ScanStatus.SUCCESS
    assert result.processed_count == 1
    assert result.failed_count == 0
    assert snapshot["counts"]["unique"] == 1


@pytest.mark.asyncio
async def test_scan_keeps_email_when_llm_returns_empty_twice(settings, password_env):
    model = DeepSeekLanguageModel(settings)
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
    ]

    class Completions:
        async def create(self, **kwargs):
            return responses.pop(0)

    model.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    app = create_application(settings, FakeEmailProvider({1: [make_email()]}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)

    assert result.status == ScanStatus.SUCCESS
    assert result.processed_count == 1
    assert result.failed_count == 0
    assert snapshot["counts"]["unique"] == 1


@pytest.mark.asyncio
async def test_complete_scan_persists_discard_reason_and_processed_uid(settings, password_env):
    email = make_email(subject="广告推送", body="本周优惠，点击 unsubscribe 退订")
    model = FakeLanguageModel(
        {
            "广告推送": SemanticAnalysis(
                source_suggestion="广告平台",
                category_name="其他",
                category_suggestion=None,
                semantic_score=1,
                reason="这是群发优惠信息，没有行动要求",
                summary="平台本周优惠活动",
                discard_reason_summary="群发促销内容，与你没有直接关系，也没有行动要求",
            )
        }
    )
    app = create_application(settings, FakeEmailProvider({1: [email]}), model)
    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            analysis = session.query(EmailAnalysisModel).one()
            processed = session.query(ProcessedUidModel).count()

    assert result.status == ScanStatus.SUCCESS
    assert processed == 1
    assert analysis.importance == "discardable"
    assert "没有行动要求" in analysis.discard_reason_summary


@pytest.mark.asyncio
async def test_failed_analysis_does_not_mark_uid_processed(settings, password_env):
    email = make_email(subject="处理失败")
    app = create_application(
        settings,
        FakeEmailProvider({1: [email]}),
        FakeLanguageModel(failure_subjects={"处理失败"}),
    )
    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            assert session.query(ProcessedUidModel).count() == 0
            assert session.query(EmailModel).count() == 0

    assert result.status == ScanStatus.FAILED
    assert result.failed_count == 1


@pytest.mark.asyncio
async def test_second_scan_skips_already_processed_uid(settings, password_env):
    email = make_email()
    model = FakeLanguageModel()
    app = create_application(settings, FakeEmailProvider({1: [email]}), model)
    async with app.router.lifespan_context(app):
        add_account(app)
        first = await app.state.scan_service.scan(None, 7)
        second = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            first_snapshot = json.loads(session.get(ReportModel, first.report_id).snapshot_json)
            second_snapshot = json.loads(session.get(ReportModel, second.report_id).snapshot_json)

    assert first.processed_count == 1
    assert second.skipped_count == 1
    assert model.calls == 1
    assert first_snapshot["counts"]["unique"] == 1
    assert second_snapshot["counts"]["unique"] == 1
    assert second_snapshot["time_range"] == first_snapshot["time_range"]


@pytest.mark.asyncio
async def test_repeated_scan_reuses_all_unread_analyses_in_report(settings, password_env):
    messages = [
        make_email(uid="1", subject="第一封"),
        make_email(uid="2", subject="第二封"),
        make_email(uid="3", subject="第三封"),
    ]
    model = FakeLanguageModel()
    app = create_application(settings, FakeEmailProvider({1: messages}), model)
    async with app.router.lifespan_context(app):
        add_account(app)
        first = await app.state.scan_service.scan(None, 7)
        second = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, second.report_id).snapshot_json)

    report_items = [
        item
        for categories in snapshot["tree"].values()
        for items in categories.values()
        for item in items
    ] + snapshot["discardable"]
    assert first.processed_count == 3
    assert second.processed_count == 0
    assert second.skipped_count == 3
    assert model.calls == 3
    assert snapshot["counts"]["unique"] == 3
    assert len(report_items) == 3


@pytest.mark.asyncio
async def test_multi_account_failure_returns_partial_report(settings, password_env):
    app = create_application(
        settings,
        FakeEmailProvider({1: [make_email()]}, failures={2: "登录失败"}),
        FakeLanguageModel(),
    )
    async with app.router.lifespan_context(app):
        add_account(app, "正常邮箱", "one@example.com")
        add_account(app, "失败邮箱", "two@example.com")
        result = await app.state.scan_service.scan(None, 7)

    assert result.status == ScanStatus.PARTIAL_SUCCESS
    assert result.processed_count == 1
    assert any(error["account"] == "失败邮箱" for error in result.errors)


@pytest.mark.asyncio
async def test_empty_successful_account_still_makes_multi_account_scan_partial(settings, password_env):
    app = create_application(
        settings,
        FakeEmailProvider({1: []}, failures={2: "登录失败"}),
        FakeLanguageModel(),
    )
    async with app.router.lifespan_context(app):
        add_account(app, "空邮箱", "one@example.com")
        add_account(app, "失败邮箱", "two@example.com")
        result = await app.state.scan_service.scan(None, 7)

    assert result.status == ScanStatus.PARTIAL_SUCCESS


@pytest.mark.asyncio
async def test_duplicate_message_is_shown_once_with_both_accounts(settings, password_env):
    first = make_email(uid="1", message_id="<same@example.com>")
    second = make_email(uid="2", message_id="<same@example.com>")
    app = create_application(
        settings,
        FakeEmailProvider({1: [first], 2: [second]}),
        FakeLanguageModel(),
    )
    async with app.router.lifespan_context(app):
        add_account(app, "邮箱一", "one@example.com")
        add_account(app, "邮箱二", "two@example.com")
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)

    items = [item for categories in snapshot["tree"].values() for group in categories.values() for item in group]
    assert len(items) == 1
    assert set(items[0]["account_names"]) == {"邮箱一", "邮箱二"}


@pytest.mark.asyncio
async def test_later_duplicate_scan_mentions_account_from_previous_scan(settings, password_env):
    first = make_email(uid="1", message_id="<same-across-scans@example.com>")
    second = make_email(uid="2", message_id="<same-across-scans@example.com>")
    provider = FakeEmailProvider({1: [first], 2: []})
    app = create_application(settings, provider, FakeLanguageModel())
    async with app.router.lifespan_context(app):
        add_account(app, "邮箱一", "one@example.com")
        add_account(app, "邮箱二", "two@example.com")
        await app.state.scan_service.scan([1], 7)
        provider.messages_by_account = {1: [], 2: [second]}
        result = await app.state.scan_service.scan([2], 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)

    items = [item for categories in snapshot["tree"].values() for group in categories.values() for item in group]
    assert set(items[0]["account_names"]) == {"邮箱一", "邮箱二"}


@pytest.mark.asyncio
async def test_report_snapshot_does_not_change_after_analysis_update(settings, password_env):
    app = create_application(settings, FakeEmailProvider({1: [make_email()]}), FakeLanguageModel())
    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            report = session.get(ReportModel, result.report_id)
            original_snapshot = report.snapshot_json
            analysis = session.query(EmailAnalysisModel).one()
            analysis.summary = "后来改过的摘要"
            session.commit()
            session.refresh(report)
            assert report.snapshot_json == original_snapshot


@pytest.mark.asyncio
async def test_report_orders_important_before_general_and_uses_received_time(settings, password_env):
    old_sent = datetime(2019, 1, 1, tzinfo=timezone.utc)
    recent_received = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)
    general = make_email(uid="1", subject="一般", body="普通信息", links=())
    important = make_email(
        uid="2",
        subject="重要",
        body="请确认并于 2026-08-14 前提交。",
        sent_at=old_sent,
        received_at=recent_received,
        links=(),
    )
    model = FakeLanguageModel(
        {
            "一般": SemanticAnalysis("测试来源", "通知", None, 4, "一般", "一般摘要", None),
            "重要": SemanticAnalysis("测试来源", "通知", None, 5, "重要", "重要摘要", None),
        }
    )
    app = create_application(settings, FakeEmailProvider({1: [general, important]}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)

    items = next(iter(next(iter(snapshot["tree"].values())).values()))
    assert [item["importance"] for item in items] == ["important", "general"]
    assert snapshot["time_range"]["latest"] == recent_received.isoformat()


@pytest.mark.asyncio
async def test_report_overview_includes_every_important_email(settings, password_env):
    messages = [
        make_email(
            uid=str(index),
            subject=f"重要{index}",
            body="请确认并于 2026-08-14 前提交。",
            links=(),
        )
        for index in range(1, 5)
    ]
    model = FakeLanguageModel(
        {
            f"重要{index}": SemanticAnalysis(
                "测试来源", "通知", None, 5, "有行动", f"重要{index} 的摘要", None
            )
            for index in range(1, 5)
        }
    )
    app = create_application(settings, FakeEmailProvider({1: messages}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)

    for index in range(1, 5):
        assert f"重要{index} 的摘要" in snapshot["overview"]


@pytest.mark.asyncio
async def test_report_saves_ai_link_summaries_and_filters_unsafe_links(settings, password_env):
    email = make_email(
        links=("https://example.com/register", "javascript:alert(1)"),
    )
    model = FakeLanguageModel(
        {
            "测试邮件": SemanticAnalysis(
                "测试来源",
                "通知",
                None,
                3,
                "需要确认",
                "邮件摘要",
                None,
                (AnalyzedLink("https://example.com/register", "活动报名页面"),),
            )
        }
    )
    app = create_application(settings, FakeEmailProvider({1: [email]}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)

    item = next(iter(next(iter(snapshot["tree"].values())).values()))[0]
    assert item["links"] == [
        {"url": "https://example.com/register", "summary": "活动报名页面"}
    ]


@pytest.mark.asyncio
async def test_seeded_source_and_existing_category_do_not_create_suggestions(settings, password_env):
    email = make_email(sender="aae.notice@polyu.edu.hk", links=())
    model = FakeLanguageModel(
        {
            "测试邮件": SemanticAnalysis(
                "香港理工大学学生事务处",
                "通知",
                "通知",
                3,
                "学校通知",
                "学校摘要",
                None,
            )
        }
    )
    app = create_application(settings, FakeEmailProvider({1: [email]}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            analysis = session.query(EmailAnalysisModel).one()
            suggestions = session.query(ClassificationSuggestionModel).all()

    assert analysis.source_name == "香港理工大学"
    assert suggestions == []


@pytest.mark.asyncio
async def test_unknown_source_uses_stable_domain_while_ai_name_is_only_suggested(
    settings,
    password_env,
):
    messages = [
        make_email(uid="1", subject="第一封", sender="notice@news.example.org", links=()),
        make_email(uid="2", subject="第二封", sender="events@news.example.org", links=()),
    ]
    model = FakeLanguageModel(
        {
            "第一封": SemanticAnalysis(
                "示例机构通知中心", "通知", None, 3, "机构通知", "第一封摘要", None
            ),
            "第二封": SemanticAnalysis(
                "示例机构活动办公室", "活动", None, 3, "机构活动", "第二封摘要", None
            ),
        }
    )
    app = create_application(settings, FakeEmailProvider({1: messages}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        result = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            snapshot = json.loads(session.get(ReportModel, result.report_id).snapshot_json)
            suggestions = session.query(ClassificationSuggestionModel).all()

    assert list(snapshot["tree"]) == ["news.example.org"]
    assert len([item for item in suggestions if item.suggestion_type == "source"]) == 1
    assert suggestions[0].proposed_name == "示例机构通知中心"


@pytest.mark.asyncio
async def test_only_explicit_new_category_suggestion_enters_confirmation_queue(
    settings,
    password_env,
):
    messages = [
        make_email(uid="1", subject="错误细分类", links=()),
        make_email(uid="2", subject="明确新类别", links=()),
    ]
    model = FakeLanguageModel(
        {
            "错误细分类": SemanticAnalysis(
                "测试来源", "学术讲座", None, 3, "属于学术内容", "讲座摘要", None
            ),
            "明确新类别": SemanticAnalysis(
                "测试来源", "其他", "志愿服务", 3, "现有类别不适用", "义工摘要", None
            ),
        }
    )
    app = create_application(settings, FakeEmailProvider({1: messages}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            category_suggestions = session.query(ClassificationSuggestionModel).filter_by(
                suggestion_type="category"
            ).all()
            analyses = session.query(EmailAnalysisModel).order_by(EmailAnalysisModel.id).all()

    assert [analysis.category_name for analysis in analyses] == ["其他", "其他"]
    assert [suggestion.proposed_name for suggestion in category_suggestions] == ["志愿服务"]


@pytest.mark.asyncio
async def test_local_read_mail_is_excluded_until_removed(settings, password_env):
    email = make_email(links=())
    model = FakeLanguageModel()
    app = create_application(settings, FakeEmailProvider({1: [email]}), model)

    async with app.router.lifespan_context(app):
        add_account(app)
        first = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            from app.infrastructure.models import ReportModel

            first_snapshot = json.loads(session.get(ReportModel, first.report_id).snapshot_json)
            email_id = next(
                item["email_id"]
                for categories in first_snapshot["tree"].values()
                for items in categories.values()
                for item in items
            )

        app.state.read_mail_service.mark(email_id)
        second = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            second_snapshot = json.loads(session.get(ReportModel, second.report_id).snapshot_json)
            assert session.query(LocalReadMailModel).count() == 1

        app.state.read_mail_service.remove(email_id)
        third = await app.state.scan_service.scan(None, 7)
        with app.state.database.session_factory() as session:
            third_snapshot = json.loads(session.get(ReportModel, third.report_id).snapshot_json)

    assert second_snapshot["counts"]["unique"] == 0
    assert third_snapshot["counts"]["unique"] == 1
    assert model.calls == 1


def test_legacy_report_snapshot_is_adapted_without_mutating_saved_data():
    legacy_snapshot = {
        "time_range": {"earliest": "2026-08-13T10:00:00", "latest": "2026-08-13T12:00:00"},
        "overview": "旧报告",
        "tree": {
            "来源一": {
                "通知": [
                    {
                        "email_id": 1,
                        "importance": "general",
                        "received_at": "2026-08-13T12:00:00",
                        "sender_address": "notice@polyu.edu.hk",
                        "source_name": "学校官方",
                        "links": ["javascript:alert(1)", "https://example.com/action"],
                    },
                    {
                        "email_id": 2,
                        "importance": "important",
                        "received_at": "2026-08-13T10:00:00",
                        "sender_address": "events@polyu.edu.hk",
                        "source_name": "香港理工大学学生事务处",
                        "links": [],
                    },
                ]
            }
        },
        "discardable": [],
        "failed_accounts": [],
        "counts": {"unique": 2, "important": 1, "general": 1, "discardable": 0},
    }

    adapted = ReportService.prepare_snapshot(legacy_snapshot)

    assert "ordered_items" not in legacy_snapshot
    assert [item["email_id"] for item in adapted["ordered_items"]] == [2, 1]
    assert adapted["ordered_items"][1]["links"] == [
        {"url": "https://example.com/action", "summary": "example.com"}
    ]
    assert {item["source_name"] for item in adapted["ordered_items"]} == {"香港理工大学"}
    assert list(adapted["tree"]) == ["香港理工大学"]


def test_current_snapshot_keeps_confirmed_source_name():
    current_snapshot = {
        "tree": {
            "用户确认的研究中心": {
                "学术": [
                    {
                        "email_id": 1,
                        "importance": "important",
                        "sender_address": "notice@research.example.org",
                        "source_name": "用户确认的研究中心",
                        "category_name": "学术",
                        "received_at": "2026-08-13T10:00:00",
                        "links": [],
                    }
                ]
            }
        },
        "ordered_items": [
            {
                "email_id": 1,
                "importance": "important",
                "sender_address": "notice@research.example.org",
                "source_name": "用户确认的研究中心",
                "category_name": "学术",
                "received_at": "2026-08-13T10:00:00",
                "links": [],
            }
        ],
        "discardable": [],
    }

    adapted = ReportService.prepare_snapshot(current_snapshot)

    assert adapted["ordered_items"][0]["source_name"] == "用户确认的研究中心"
    assert list(adapted["tree"]) == ["用户确认的研究中心"]
