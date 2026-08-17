from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import SuggestionStatus, SuggestionType
from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.models import (
    CategoryModel,
    ClassificationSuggestionModel,
    SourceModel,
    SourceRuleModel,
)


CATEGORY_SEEDS = (
    ("通知", "学校或机构的正式通告、政策和截止提醒"),
    ("学术", "课程、选课、成绩、论文和讲座"),
    ("活动", "讲座、社团、招新和社交活动"),
    ("招聘", "职位推送、面试邀约和实习机会"),
    ("私人信件", "具体个人发来的信件"),
    ("账单缴费", "学费、住宿费、订阅和其他款项"),
    ("系统与账号", "密码、登录、安全和服务变更"),
    ("其他", "无法归入已有类别的邮件"),
)

SOURCE_SEEDS = (
    ("香港理工大学", "domain", "polyu.edu.hk"),
    ("网易邮箱", "domain", "service.netease.com"),
    ("JobsDB", "domain", "jobsdb.com"),
)


class ClassificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def seed_categories(self) -> None:
        existing = set(self.session.scalars(select(CategoryModel.name)))
        for display_order, (name, description) in enumerate(CATEGORY_SEEDS, start=1):
            if name not in existing:
                self.session.add(
                    CategoryModel(
                        name=name,
                        description=description,
                        display_order=display_order,
                    )
                )
        self._seed_sources()
        self._remove_invalid_pending_suggestions()

    def active_categories(self) -> list[CategoryModel]:
        return list(
            self.session.scalars(
                select(CategoryModel)
                .where(CategoryModel.is_active.is_(True))
                .order_by(CategoryModel.display_order, CategoryModel.id)
            )
        )

    def category_by_name(self, name: str) -> CategoryModel:
        category = self.session.scalar(
            select(CategoryModel).where(
                CategoryModel.name == name,
                CategoryModel.is_active.is_(True),
            )
        )
        if category is None:
            category = self.session.scalar(select(CategoryModel).where(CategoryModel.name == "其他"))
        if category is None:
            raise ResourceNotFoundError("缺少兜底分类“其他”")
        return category

    def category_exists(self, name: str) -> bool:
        normalized_name = name.strip()
        if not normalized_name:
            return False
        return self.session.scalar(
            select(CategoryModel.id).where(
                CategoryModel.name == normalized_name,
                CategoryModel.is_active.is_(True),
            )
        ) is not None

    def match_source(self, sender_address: str) -> SourceModel | None:
        address = sender_address.lower()
        domain = address.rsplit("@", 1)[-1] if "@" in address else ""
        rules = self.session.scalars(
            select(SourceRuleModel)
            .options(selectinload(SourceRuleModel.source))
            .where(SourceRuleModel.is_active.is_(True))
            .order_by(SourceRuleModel.id)
        )
        for rule in rules:
            if not rule.source.is_active:
                continue
            pattern = rule.pattern.lower()
            if rule.match_type == "address" and address == pattern:
                return rule.source
            if rule.match_type == "domain" and (domain == pattern or domain.endswith(f".{pattern}")):
                return rule.source
        return None

    def create_suggestion(
        self,
        suggestion_type: SuggestionType,
        proposed_name: str | None,
        proposed_pattern: str | None,
        email_id: int,
        reason: str,
    ) -> None:
        if not proposed_name or not proposed_name.strip():
            return
        normalized_name = proposed_name.strip()
        if suggestion_type == SuggestionType.CATEGORY:
            category_exists = self.session.scalar(
                select(CategoryModel.id).where(CategoryModel.name == normalized_name)
            )
            if category_exists is not None:
                return
        if suggestion_type == SuggestionType.SOURCE and proposed_pattern:
            existing_source = self.match_source(f"source@{proposed_pattern.strip().lower()}")
            if existing_source is not None:
                return
        duplicate = self.session.scalar(
            select(ClassificationSuggestionModel.id).where(
                ClassificationSuggestionModel.suggestion_type == suggestion_type.value,
                ClassificationSuggestionModel.status == SuggestionStatus.PENDING.value,
                (
                    ClassificationSuggestionModel.proposed_pattern == proposed_pattern
                    if suggestion_type == SuggestionType.SOURCE and proposed_pattern
                    else ClassificationSuggestionModel.proposed_name == normalized_name
                ),
            )
        )
        if duplicate is None:
            self.session.add(
                ClassificationSuggestionModel(
                    suggestion_type=suggestion_type.value,
                    proposed_name=normalized_name,
                    proposed_pattern=proposed_pattern,
                    email_id=email_id,
                    reason=reason,
                    status=SuggestionStatus.PENDING.value,
                )
            )

    def display_source_name(self, sender_address: str) -> str:
        source = self.match_source(sender_address)
        if source:
            return source.name
        if "@" in sender_address:
            return sender_address.rsplit("@", 1)[-1].strip().lower()
        return "未知来源"

    def _seed_sources(self) -> None:
        for source_name, match_type, pattern in SOURCE_SEEDS:
            source = self.session.scalar(select(SourceModel).where(SourceModel.name == source_name))
            if source is None:
                source = SourceModel(name=source_name)
                self.session.add(source)
                self.session.flush()
            rule_exists = self.session.scalar(
                select(SourceRuleModel.id).where(
                    SourceRuleModel.source_id == source.id,
                    SourceRuleModel.match_type == match_type,
                    SourceRuleModel.pattern == pattern,
                )
            )
            if rule_exists is None:
                self.session.add(
                    SourceRuleModel(
                        source_id=source.id,
                        match_type=match_type,
                        pattern=pattern,
                    )
                )

    def _remove_invalid_pending_suggestions(self) -> None:
        category_names = select(CategoryModel.name)
        self.session.execute(
            delete(ClassificationSuggestionModel).where(
                ClassificationSuggestionModel.suggestion_type == SuggestionType.CATEGORY.value,
                ClassificationSuggestionModel.status == SuggestionStatus.PENDING.value,
                ClassificationSuggestionModel.proposed_name.in_(category_names),
            )
        )
        source_patterns = select(SourceRuleModel.pattern)
        self.session.execute(
            delete(ClassificationSuggestionModel).where(
                ClassificationSuggestionModel.suggestion_type == SuggestionType.SOURCE.value,
                ClassificationSuggestionModel.status == SuggestionStatus.PENDING.value,
                ClassificationSuggestionModel.proposed_pattern.in_(source_patterns),
            )
        )

    def list_suggestions(self, status: str | None = None) -> list[ClassificationSuggestionModel]:
        statement = select(ClassificationSuggestionModel).order_by(
            ClassificationSuggestionModel.created_at.desc()
        )
        if status:
            statement = statement.where(ClassificationSuggestionModel.status == status)
        return list(self.session.scalars(statement))
