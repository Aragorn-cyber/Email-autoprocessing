from app.infrastructure.models import ImportantMailModel
from app.infrastructure.persistence.email_mark_repository import EmailMarkRepository


class ImportantMailRepository(EmailMarkRepository):
    model = ImportantMailModel
    list_label = "重要邮件名单"  # ??????
