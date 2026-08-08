class AuthenticationError(Exception):
    """Credentials or token material could not be authenticated."""


class DuplicateEmailError(Exception):
    """A normalized email is already registered."""


class InactiveUserError(Exception):
    """A valid identity belongs to a disabled account."""
