# -*- coding: utf-8 -*-
"""
Authentication Domain Service.
Coordinates registration, login, and identity verification.
Depends on abstractions (IUserRepository, IPasswordHasher, ITokenProvider).
"""

import uuid
from typing import Dict, Any, Tuple, Optional
from neev_backend.core.interfaces.auth_interface import IPasswordHasher, ITokenProvider
from neev_backend.core.interfaces.repository_interface import IUserRepository
from neev_backend.core.exceptions import ConflictError, AuthenticationError, EntityNotFoundError

class AuthService:
    """Manages student user authentication and token issuance."""

    def __init__(
        self,
        user_repo: IUserRepository,
        hasher: IPasswordHasher,
        token_provider: ITokenProvider
    ):
        self.user_repo = user_repo
        self.hasher = hasher
        self.token_provider = token_provider

    def register(self, name: str, email: str, password: str) -> Tuple[Dict[str, Any], str]:
        email_clean = email.strip().lower()
        existing = self.user_repo.get_by_email(email_clean)
        if existing:
            raise ConflictError("An account with this email address already exists. Please log in.")

        user_id = f"user_{uuid.uuid4().hex[:12]}"
        password_hash = self.hasher.hash_password(password)
        user = self.user_repo.create(user_id=user_id, email=email_clean, name=name.strip(), password_hash=password_hash)

        token = self.token_provider.create_token({
            "sub": user["id"],
            "email": user["email"],
            "name": user["name"]
        })
        return user, token

    def login(self, email: str, password: str) -> Tuple[Dict[str, Any], str]:
        email_clean = email.strip().lower()
        user = self.user_repo.get_by_email(email_clean)
        if not user:
            raise AuthenticationError("Invalid email or password.")

        if not self.hasher.verify_password(password, user["password_hash"]):
            raise AuthenticationError("Invalid email or password.")

        token = self.token_provider.create_token({
            "sub": user["id"],
            "email": user["email"],
            "name": user["name"]
        })
        return user, token

    def verify_token(self, token: str) -> Dict[str, Any]:
        return self.token_provider.decode_token(token)

    def get_current_user(self, raw_token: str) -> Dict[str, Any]:
        payload = self.verify_token(raw_token)
        user_id = payload["sub"]
        user = self.user_repo.get_by_id(user_id)
        if not user:
            # Handle mock demo user
            if user_id == "user_demo":
                return {
                    "is_authenticated": True,
                    "user": {"id": "user_demo", "name": payload.get("name", "Demo Student"), "email": payload.get("email", "demo@example.com")},
                    "claims": payload
                }
            raise EntityNotFoundError("User not found.")

        return {
            "is_authenticated": True,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "created_at": user.get("created_at")
            },
            "claims": payload
        }
