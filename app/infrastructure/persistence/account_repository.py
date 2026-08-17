from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConfigurationError, ResourceNotFoundError
from app.domain.entities import MailboxConnection
from app.infrastructure.credentials import EnvironmentCredentialProvider
from app.infrastructure.models import MailboxAccountModel


class MailboxAccountRepository:
    def __init__(
        self,
        session: Session,
        credential_provider: EnvironmentCredentialProvider | None = None,
    ):
        self.session = session
        self.credential_provider = credential_provider or EnvironmentCredentialProvider()

    def list(self, active_only: bool = False) -> list[MailboxAccountModel]:
        statement = select(MailboxAccountModel).order_by(MailboxAccountModel.id)
        if active_only:
            statement = statement.where(MailboxAccountModel.is_active.is_(True))
        return list(self.session.scalars(statement))

    def get(self, account_id: int) -> MailboxAccountModel:
        account = self.session.get(MailboxAccountModel, account_id)
        if account is None:
            raise ResourceNotFoundError(f"邮箱账号 {account_id} 不存在")
        return account

    def create(self, **values: object) -> MailboxAccountModel:
        account = MailboxAccountModel(**values)
        self.session.add(account)
        self.session.flush()
        return account

    def update(self, account_id: int, **values: object) -> MailboxAccountModel:
        account = self.get(account_id)
        for key, value in values.items():
            setattr(account, key, value)
        self.session.flush()
        return account

    def connection_for(self, account: MailboxAccountModel) -> MailboxConnection:
        password = self.credential_provider.get(account.password_env_name)
        if not password:
            raise ConfigurationError(
                f"邮箱 {account.email_address} 缺少环境变量 {account.password_env_name}"
            )
        return MailboxConnection(
            account_id=account.id,
            account_name=account.name,
            email_address=account.email_address,
            host=account.imap_host,
            port=account.imap_port,
            username=account.username,
            password=password,
            folder=account.folder,
        )
