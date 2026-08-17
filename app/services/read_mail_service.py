from app.infrastructure.persistence.read_mail_repository import LocalReadMailRepository
from app.services.email_mark_service import EmailMarkService


class LocalReadMailService(EmailMarkService):
    repository_class = LocalReadMailRepository
