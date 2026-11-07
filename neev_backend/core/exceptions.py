# -*- coding: utf-8 -*-
"""
Domain Exceptions for Neev Platform.
Decouples domain business errors from HTTP transport layer.
"""

class NeevException(Exception):
    """Base domain exception."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class EntityNotFoundError(NeevException):
    """Raised when a requested entity (User, Profile, College) is not found."""
    pass

class AuthenticationError(NeevException):
    """Raised when authentication credentials or token are invalid or expired."""
    pass

class AuthorizationError(NeevException):
    """Raised when a user attempts to access a resource belonging to another tenant."""
    pass

class ValidationError(NeevException):
    """Raised when domain business rules are violated by input data."""
    pass

class ConflictError(NeevException):
    """Raised on state conflicts, such as duplicate user registration."""
    pass
