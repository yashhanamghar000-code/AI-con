# -*- coding: utf-8 -*-
from .auth_routes import router as auth_router
from .onboarding_routes import router as onboarding_router
from .stream_routes import router as stream_router
from .chat_routes import router as chat_router
from .college_routes import router as college_router

__all__ = [
    "auth_router",
    "onboarding_router",
    "stream_router",
    "chat_router",
    "college_router"
]
