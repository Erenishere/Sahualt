class VisualError(Exception):
    """Expected failure at the retrieval boundary."""


class InvalidImageError(VisualError):
    pass


class ConfigurationError(VisualError):
    pass


class ModelLoadError(VisualError):
    pass


class IndexCompatibilityError(VisualError):
    pass


class EmptyIndexError(VisualError):
    pass


class DatasetError(VisualError):
    pass
