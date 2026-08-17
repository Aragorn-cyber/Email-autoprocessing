from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError
from app.infrastructure.persistence import MailboxAccountRepository


class AccountService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def list_accounts(self):
        with self.session_factory() as session:
            return MailboxAccountRepository(session).list()

    def create_account(self, values: dict):
        with self.session_factory() as session:
            repository = MailboxAccountRepository(session)
            try:
                account = repository.create(**values)
                session.commit()
                return account
            except IntegrityError as exc:
                session.rollback()
                raise ConflictError("该邮箱账号已经存在") from exc

    def update_account(self, account_id: int, changes: dict):
        with self.session_factory() as session:
            account = MailboxAccountRepository(session).update(account_id, **changes)
            session.commit()
            return account
