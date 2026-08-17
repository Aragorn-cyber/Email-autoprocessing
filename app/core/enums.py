from enum import StrEnum


class ImportanceLevel(StrEnum):
    IMPORTANT = "important"
    GENERAL = "general"
    DISCARDABLE = "discardable"


class ScanStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class SuggestionType(StrEnum):
    SOURCE = "source"
    CATEGORY = "category"


class SuggestionStatus(StrEnum):
    PENDING = "pending"

