class NotFoundError(Exception):
    """The requested record does not exist."""


class ConflictError(Exception):
    """The change would violate a uniqueness rule."""


class InvalidReferenceError(Exception):
    """A foreign key points at a record that does not exist."""


class InvalidPrefixError(ValueError):
    """A reference prefix that is not registered with the sequence service."""
