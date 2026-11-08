# -*- coding: utf-8 -*-
"""
Dependency Injection Container (Service Locator / IoC).
Adheres strictly to Dependency Inversion Principle (DIP).
Wires concrete implementations to abstractions in a single composable location.
"""

from typing import Optional
from neev_backend.config.settings import settings
from db import db_manager as unified_db_manager
from neev_backend.services.auth.hasher import Pbkdf2PasswordHasher
from neev_backend.services.auth.token_service import JwtTokenProvider
from neev_backend.services.auth.auth_service import AuthService
from neev_backend.services.database.user_repository import UserRepository
from neev_backend.services.database.profile_repository import ProfileRepository
from neev_backend.services.database.chat_repository import ChatRepository
from neev_backend.services.onboarding.stream_engine import StreamRecommendationEngine
from neev_backend.services.onboarding.aptitude_service import AptitudeService
from neev_backend.services.onboarding.onboarding_service import OnboardingService
from neev_backend.services.cutoff.search_service import CutoffService
from neev_backend.services.cutoff.resolver_service import CollegeResolverService
from neev_backend.services.chat.context_builder import StudentContextBuilder
from neev_backend.services.chat.chat_service import ChatService

class Container:
    """Centralized Dependency Injection Container for Neev Platform."""

    def __init__(self, db_manager=None):
        # 1. Infrastructure & Persistence
        self.db_manager = db_manager or unified_db_manager
        self.user_repo = UserRepository(self.db_manager)
        self.profile_repo = ProfileRepository(self.db_manager)
        self.chat_repo = ChatRepository(self.db_manager)

        # 2. Security & Tokens
        self.hasher = Pbkdf2PasswordHasher()
        self.token_provider = JwtTokenProvider()

        # 3. Domain Services
        self.auth_service = AuthService(
            user_repo=self.user_repo,
            hasher=self.hasher,
            token_provider=self.token_provider
        )

        self.stream_engine = StreamRecommendationEngine()
        self.aptitude_service = AptitudeService()
        self.onboarding_service = OnboardingService(
            profile_repo=self.profile_repo,
            stream_engine=self.stream_engine
        )

        self.cutoff_service = CutoffService()
        self.resolver_service = CollegeResolverService()

        self.context_builder = StudentContextBuilder()
        self.chat_service = ChatService(
            chat_repo=self.chat_repo,
            profile_repo=self.profile_repo,
            user_repo=self.user_repo,
            token_provider=self.token_provider,
            context_builder=self.context_builder
        )

# Global default container instance
container = Container()
