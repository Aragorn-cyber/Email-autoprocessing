class ApplicationError(Exception):
    pass


class ResourceNotFoundError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class ConfigurationError(ApplicationError):
    pass


class ExternalServiceError(ApplicationError):
    pass


class AnalysisValidationError(ApplicationError):
    pass
