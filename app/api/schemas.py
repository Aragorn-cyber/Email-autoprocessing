from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email_address: EmailStr
    imap_host: str = Field(min_length=1, max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=320)
    password_env_name: str = Field(min_length=1, max_length=120)
    folder: str = Field(default="INBOX", min_length=1, max_length=255)
    scan_window_days: int = Field(default=7, ge=1, le=90)


class AccountUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    imap_host: str | None = Field(default=None, min_length=1, max_length=255)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=320)
    password_env_name: str | None = Field(default=None, min_length=1, max_length=120)
    folder: str | None = Field(default=None, min_length=1, max_length=255)
    scan_window_days: int | None = Field(default=None, ge=1, le=90)
    is_active: bool | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email_address: str
    imap_host: str
    imap_port: int
    username: str
    password_env_name: str
    folder: str
    scan_window_days: int
    is_active: bool


class MarkReadBulkRequest(BaseModel):
    email_ids: list[int] = Field(min_length=1)


class ScanRequest(BaseModel):
    account_ids: list[int] | None = None
    window_days: int | None = Field(default=None, ge=1, le=90)


class ScanResponse(BaseModel):
    scan_id: int
    report_id: int
    status: str
    fetched_count: int
    processed_count: int
    skipped_count: int
    failed_count: int
    errors: list[dict[str, str]]


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str
    display_order: int
    is_active: bool
