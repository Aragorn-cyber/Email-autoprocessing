from app.infrastructure.persistence.important_mail_repository import ImportantMailRepository
from app.services.email_mark_service import EmailMarkService


class ImportantMailService(EmailMarkService):
    repository_class = ImportantMailRepository
