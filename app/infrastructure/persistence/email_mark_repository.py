from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.models import EmailModel


class EmailMarkRepository:
    """本地标记名单的通用仓库：已读、重要邮件等共用同一套操作。"""

    model = None  # 子类指定标记表模型
    list_label = "标记名单"  # 子类覆盖，用于错误提示

    def __init__(self, session: Session):
        self.session = session

    def mark(self, email_id: int):
        self._require_email(email_id)
        record = self.session.scalar(
            select(self.model).where(self.model.email_id == email_id)
        )
        if record is None:
            record = self.model(email_id=email_id)
            self.session.add(record)
            self.session.flush()
        return record

    def remove(self, email_id: int) -> None:
        record = self.session.scalar(
            select(self.model).where(self.model.email_id == email_id)
        )
        if record is None:
            raise ResourceNotFoundError(
                f"邮件 {email_id} 不在{self.list_label}中"
            )
        self.session.delete(record)

    def mark_many(self, email_ids: list[int]) -> int:
        """批量加入标记名单，返回本次新增的数量。"""
        if not email_ids:
            return 0
        existing_emails = set(
            self.session.scalars(select(EmailModel.id).where(EmailModel.id.in_(email_ids)))
        )
        missing = [email_id for email_id in email_ids if email_id not in existing_emails]
        if missing:
            raise ResourceNotFoundError(f"邮件 {missing[0]} 不存在")
        already_marked = set(
            self.session.scalars(
                select(self.model.email_id).where(self.model.email_id.in_(email_ids))
            )
        )
        new_ids = [email_id for email_id in email_ids if email_id not in already_marked]
        if new_ids:
            self.session.add_all(self.model(email_id=email_id) for email_id in new_ids)
            self.session.flush()
        return len(new_ids)

    def remove_all(self) -> int:
        """清空标记名单，返回移除的数量。"""
        result = self.session.execute(delete(self.model))
        return result.rowcount or 0

    def marked_email_ids(self) -> set[int]:
        return set(self.session.scalars(select(self.model.email_id)))

    def is_marked(self, email_id: int) -> bool:
        return self.session.scalar(
            select(self.model.id).where(self.model.email_id == email_id)
        ) is not None

    def list(self, page: int, page_size: int):
        statement = (
            select(self.model)
            .options(
                selectinload(self.model.email).selectinload(EmailModel.account),
                selectinload(self.model.email).selectinload(EmailModel.analyses),
            )
            .order_by(self.model.marked_at.desc(), self.model.id.desc())
        )
        total_items = self.session.scalar(select(func.count()).select_from(self.model)) or 0
        records = list(
            self.session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
        )
        return records, total_items

    def _require_email(self, email_id: int) -> None:
        if self.session.get(EmailModel, email_id) is None:
            raise ResourceNotFoundError(f"邮件 {email_id} 不存在")
