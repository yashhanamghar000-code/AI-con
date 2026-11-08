# -*- coding: utf-8 -*-
"""
Authentication & Cryptographic Interfaces.
Adheres to Interface Segregation Principle (ISP) and Dependency Inversion Principle (DIP).
"""

from typing import Protocol, Dict, Any, Optional

class IPasswordHasher(Protocol):
    """Abstraction for password hashing and verification."""
    def hash_password(self, password: str) -> str:
        """Derive cryptographic hash from plaintext password."""
        ...

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify plaintext password against stored hash."""
        ...

class ITokenProvider(Protocol):
    """Abstraction for JWT access token encoding and decoding."""
    def create_token(self, payload: Dict[str, Any], expires_days: Optional[int] = None) -> str:
        """Encode token containing claims and expiration."""
        ...

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and cryptographically verify claims and expiration."""
        ...

    def extract_token_from_header(self, authorization: Optional[str] = None, token_param: Optional[str] = None) -> Optional[str]:
        """Extract clean token string from Authorization header or param."""
        ...
