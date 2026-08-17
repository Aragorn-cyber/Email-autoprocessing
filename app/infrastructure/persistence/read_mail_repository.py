from app.infrastructure.models import LocalReadMailModel
from app.infrastructure.persistence.email_mark_repository import EmailMarkRepository


class LocalReadMailRepository(EmailMarkRepository):
    model = LocalReadMailModel
    list_label = "本地已读名单"  # ??????
