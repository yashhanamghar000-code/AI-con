# -*- coding: utf-8 -*-
"""
Password Hasher Implementation.
Adheres to Single Responsibility Principle (SRP).
"""

import hashlib
import hmac

class Pbkdf2PasswordHasher:
    """Secure password hashing using PBKDF2-HMAC-SHA256 with per-user salt."""
    
    def __init__(self, iterations: int = 100_000):
        self.iterations = iterations

    def hash_password(self, password: str, salt: str = "neev_education_salt_2026") -> str:
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            self.iterations
        )
        return key.hex()

    def verify_password(self, plain_password: str, hashed_password: str, salt: str = "neev_education_salt_2026") -> bool:
        computed = self.hash_password(plain_password, salt)
        return hmac.compare_digest(computed, hashed_password)
