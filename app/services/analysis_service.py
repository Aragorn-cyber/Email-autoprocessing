from app.core.enums import ImportanceLevel
from app.core.exceptions import AnalysisValidationError
from app.core.link_policy import report_links
from app.domain.entities import AnalyzedLink, CompletedAnalysis, FetchedEmail
from app.domain.interfaces import LanguageModelClient
from app.infrastructure.persistence import ClassificationRepository
from app.services.scoring_service import RuleScoringService


class EmailAnalysisService:
    def __init__(
        self,
        classification_repository: ClassificationRepository,
        scoring_service: RuleScoringService,
        language_model: LanguageModelClient,
    ):
        self.classification_repository = classification_repository
        self.scoring_service = scoring_service
        self.language_model = language_model

    async def analyze(self, email: FetchedEmail) -> CompletedAnalysis:
        categories = self.classification_repository.active_categories()
        semantic = await self.language_model.analyze_email(
            email,
            tuple(category.name for category in categories),
        )
        if not 0 <= semantic.semantic_score <= 5:
            raise AnalysisValidationError("AI 语义分必须在 0 到 5 之间")
        if not semantic.summary.strip():
            raise AnalysisValidationError("邮件摘要不能为空")

        rule_score = self.scoring_service.score(email)
        total_score = rule_score.score + semantic.semantic_score
        importance = self.scoring_service.importance_for(total_score)
        discard_reason = semantic.discard_reason_summary
        if importance == ImportanceLevel.DISCARDABLE:
            discard_reason = self._build_discard_reason(
                semantic.discard_reason_summary,
                semantic.reason,
                tuple(hit.description for hit in rule_score.hits if hit.score < 0),
            )
            if not discard_reason:
                raise AnalysisValidationError("可丢弃邮件缺少归类原因摘要")

        source = self.classification_repository.match_source(email.sender_address)
        source_name = source.name if source else self._sender_source(email)
        category = self.classification_repository.category_by_name(semantic.category_name)
        category_suggestion = semantic.category_suggestion
        if category_suggestion and self.classification_repository.category_exists(
            category_suggestion
        ):
            category_suggestion = None
        link_summaries = self._validated_link_summaries(email, semantic.link_summaries)

        return CompletedAnalysis(
            source_id=source.id if source else None,
            source_name=source_name,
            category_id=category.id,
            category_name=category.name,
            rule_score=rule_score.score,
            semantic_score=semantic.semantic_score,
            total_score=total_score,
            importance=importance,
            reason=semantic.reason.strip(),
            summary=semantic.summary.strip(),
            discard_reason_summary=discard_reason,
            rule_hits=rule_score.hits,
            link_summaries=link_summaries,
            source_suggestion=semantic.source_suggestion,
            category_suggestion=category_suggestion,
        )

    @staticmethod
    def _build_discard_reason(
        model_summary: str | None,
        model_reason: str,
        negative_rule_reasons: tuple[str, ...],
    ) -> str:
        if model_summary and model_summary.strip():
            return model_summary.strip()
        pieces = [*negative_rule_reasons, model_reason.strip()]
        meaningful = [piece for piece in pieces if piece]
        return "；".join(dict.fromkeys(meaningful))[:240]

    @staticmethod
    def _sender_source(email: FetchedEmail) -> str:
        return EmailAnalysisService._sender_domain(email.sender_address) or "未知来源"

    @staticmethod
    def _sender_domain(address: str) -> str | None:
        return address.rsplit("@", 1)[-1].lower() if "@" in address else None

    @staticmethod
    def _validated_link_summaries(
        email: FetchedEmail,
        model_links: tuple[AnalyzedLink, ...],
    ) -> tuple[AnalyzedLink, ...]:
        safe_links = report_links(list(email.extracted_links))
        summaries = {
            item.url: item.summary.strip()
            for item in model_links
            if item.url in safe_links and item.summary.strip()
        }
        return tuple(
            AnalyzedLink(url=url, summary=summaries[url])
            for url in safe_links
            if url in summaries
        )
