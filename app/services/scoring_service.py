import re

from app.core.config import ApplicationSettings
from app.core.enums import ImportanceLevel
from app.domain.entities import FetchedEmail, RuleHit, RuleScore


class RuleScoringService:
    DEADLINE_PATTERNS = (
        re.compile(r"\b(?:deadline|due|before|by)\b", re.IGNORECASE),
        re.compile(r"(?:截止|截至|限期|最迟|之前办理|前办理)"),
        re.compile(r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b"),
        re.compile(r"\b\d{1,2}[:：]\d{2}\b"),
    )
    ACTION_PATTERNS = (
        re.compile(r"(?:请回复|请确认|须于|务必|请提交|请填写|请参加)"),
        re.compile(r"\b(?:reply|confirm|submit|required action|action required)\b", re.IGNORECASE),
    )
    BULK_PATTERNS = (
        re.compile(r"(?:退订|取消订阅|群发|推广|广告)"),
        re.compile(r"\b(?:unsubscribe|newsletter|promotional|advertisement)\b", re.IGNORECASE),
    )

    def __init__(self, settings: ApplicationSettings):
        self.settings = settings

    def score(self, email: FetchedEmail) -> RuleScore:
        text = f"{email.subject}\n{email.body_text}"
        sender = email.sender_address.lower()
        hits: list[RuleHit] = []

        if self._matches_sender(sender, self.settings.whitelist_sender_patterns):
            hits.append(
                RuleHit("sender_whitelist", "发件人命中白名单", self.settings.whitelist_score)
            )
        if any(pattern.search(text) for pattern in self.DEADLINE_PATTERNS):
            hits.append(RuleHit("deadline", "邮件包含截止日期或明确时间", self.settings.deadline_score))
        if any(pattern.search(text) for pattern in self.ACTION_PATTERNS):
            hits.append(
                RuleHit("action_required", "邮件包含明确行动要求", self.settings.action_required_score)
            )
        if self._matches_sender(sender, self.settings.blacklist_sender_patterns):
            hits.append(
                RuleHit("sender_blacklist", "发件人命中广告黑名单", self.settings.blacklist_score)
            )
        if any(pattern.search(text) for pattern in self.BULK_PATTERNS):
            hits.append(
                RuleHit("bulk_mail", "邮件包含退订或群发特征", self.settings.bulk_mail_score)
            )

        return RuleScore(score=sum(hit.score for hit in hits), hits=tuple(hits))

    def importance_for(self, total_score: int) -> ImportanceLevel:
        if total_score >= self.settings.important_score_threshold:
            return ImportanceLevel.IMPORTANT
        if total_score >= self.settings.general_score_threshold:
            return ImportanceLevel.GENERAL
        return ImportanceLevel.DISCARDABLE

    @staticmethod
    def _matches_sender(sender: str, patterns: tuple[str, ...]) -> bool:
        domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""
        return any(
            sender == pattern
            or sender.endswith(f"@{pattern}")
            or domain == pattern
            or domain.endswith(f".{pattern}")
            for pattern in patterns
        )

