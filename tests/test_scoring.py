from app.core.enums import ImportanceLevel
from app.services.scoring_service import RuleScoringService

from tests.conftest import make_email


def test_rule_scoring_records_positive_and_negative_hits(settings):
    service = RuleScoringService(settings)
    email = make_email(
        body="请确认在 2026-08-20 前提交。点击 unsubscribe 退订。",
        sender="notice@trusted.example.com",
    )

    score = service.score(email)

    assert score.score == 7
    assert {hit.code for hit in score.hits} == {
        "sender_whitelist",
        "deadline",
        "action_required",
        "bulk_mail",
    }


def test_importance_thresholds_are_configurable(settings):
    service = RuleScoringService(settings)

    assert service.importance_for(8) == ImportanceLevel.IMPORTANT
    assert service.importance_for(4) == ImportanceLevel.GENERAL
    assert service.importance_for(3) == ImportanceLevel.DISCARDABLE
