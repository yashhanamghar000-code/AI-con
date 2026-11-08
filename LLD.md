# Neev (नींव) — Low-Level Design (LLD) Document
**Object-Oriented Design, SOLID Principles & Design Patterns**
*Version: 2.2.0 | Platform: Neev AI College & Career Foundation*

---

## 1. SOLID Principles Implementation Matrix

| Principle | Architectural Application in Neev | Concrete Classes |
| :--- | :--- | :--- |
| **S** — Single Responsibility | Each module has only one reason to change. Hasher only hashes; JWT provider only encodes/decodes; User repo only reads/writes user records; Context builder only structures student facts. | `Pbkdf2PasswordHasher`, `JwtTokenProvider`, `UserRepository`, `StudentContextBuilder` |
| **O** — Open / Closed | System open for extension via interfaces, closed for modification. New storage engines (PostgreSQL, SQLite, Mongo) or Token mechanisms (PASETO, OAuth2) plug in without modifying domain services. | `IUserRepository`, `IProfileRepository`, `ITokenProvider` |
| **L** — Liskov Substitution | Implementations of repository interfaces are completely interchangeable. `UserRepository` behaves identically whether targeting SQLite or PostgreSQL. | `UserRepository`, `ProfileRepository`, `ChatRepository` |
| **I** — Interface Segregation | Interfaces are fine-grained protocols rather than large monolithic interfaces. Classes only implement methods they consume. | `IPasswordHasher`, `ITokenProvider`, `IStreamEngine`, `IContextBuilder` |
| **D** — Dependency Inversion | High-level business logic depends entirely on abstractions (`core/interfaces/`), never on concrete third-party database or cryptography libraries. Injection via `Container`. | `AuthService`, `OnboardingService`, `ChatService`, `Container` |

---

## 2. Core Class & Interface Diagram (UML)

```mermaid
classDiagram
    class IPasswordHasher {
        <<interface>>
        +hash_password(password: str) str
        +verify_password(plain: str, hashed: str) bool
    }

    class ITokenProvider {
        <<interface>>
        +create_token(payload: dict) str
        +decode_token(token: str) dict
        +extract_token_from_header(auth, token) str
    }

    class IUserRepository {
        <<interface>>
        +get_by_email(email: str) dict
        +get_by_id(user_id: str) dict
        +create(user_id, email, name, hash) dict
    }

    class IProfileRepository {
        <<interface>>
        +get_by_user_id(user_id: str) dict
        +upsert(user_id: str, data: dict) bool
    }

    class IChatRepository {
        <<interface>>
        +add_message(user_id, role, content, ...) int
        +get_history(user_id, limit) list
    }

    class AuthService {
        -IUserRepository user_repo
        -IPasswordHasher hasher
        -ITokenProvider token_provider
        +register(name, email, password) tuple
        +login(email, password) tuple
        +get_current_user(token) dict
    }

    class OnboardingService {
        -IProfileRepository profile_repo
        -IStreamEngine stream_engine
        +save_profile(user_id, data, auth_uid) dict
        +get_profile(user_id, auth_uid) dict
        +calculate_stream(marks, interests, aptitude) dict
    }

    class ChatService {
        -IChatRepository chat_repo
        -IProfileRepository profile_repo
        -IUserRepository user_repo
        -ITokenProvider token_provider
        -IContextBuilder context_builder
        +answer_query(query, user_id, raw_token) dict
        +get_user_history(user_id, auth_uid) dict
    }

    class Container {
        +AuthService auth_service
        +OnboardingService onboarding_service
        +ChatService chat_service
        +CutoffService cutoff_service
    }

    AuthService ..> IUserRepository : depends on
    AuthService ..> IPasswordHasher : depends on
    AuthService ..> ITokenProvider : depends on
    OnboardingService ..> IProfileRepository : depends on
    ChatService ..> IChatRepository : depends on
    ChatService ..> ITokenProvider : depends on
    Container --> AuthService : injects
    Container --> OnboardingService : injects
    Container --> ChatService : injects
```

---

## 3. Design Patterns Applied

1. **Dependency Injection & IoC Container (`neev_backend/container.py`)**:
   - decouples object creation from consumption. Every service is initialized with mockable dependencies.
2. **Repository Pattern (`neev_backend/services/database/`)**:
   - Isolates the domain layer from database SQL syntax, schema details, and engine differences.
3. **Strategy Pattern (`neev_backend/services/onboarding/stream_engine.py`)**:
   - Implements multi-attribute utility calculation across PCM, PCB, Commerce, and Arts scoring strategies.
4. **Adapter Pattern (`scripts/agents/college_resolver.py`, `scripts/college_adapter.py`)**:
   - Converts sparse government educational manifests and inconsistent JSON cutoff formats into normalized internal schemas.
5. **Facade Pattern (`scripts/api_server.py`)**:
   - Provides a unified, backward-compatible HTTP interface while delegating execution to decoupled services.

---

## 4. Sequence Flows

### 4.1. Authenticated Student Chat with Profile Grounding

```mermaid
sequenceDiagram
    autonumber
    actor Student
    participant Browser as Frontend UI
    participant Router as ChatRouter (/api/chat)
    participant ChatSvc as ChatService
    participant TokenProvider as JwtTokenProvider
    participant ProfileRepo as ProfileRepository
    participant ContextBuilder as StudentContextBuilder
    participant Orch as Orchestrator
    participant DB as ChatRepository

    Student->>Browser: Enters query ("Which colleges can I get in Pune?")
    Browser->>Router: POST /api/chat [Header: Authorization Bearer JWT]
    Router->>ChatSvc: answer_query(query, user_id, raw_token)
    ChatSvc->>TokenProvider: decode_token(raw_token)
    TokenProvider-->>ChatSvc: claims (sub: user_123, email: student@test.com)
    ChatSvc->>ProfileRepo: get_by_user_id("user_123")
    ProfileRepo-->>ChatSvc: profile (category: OBC, marks: 89.5%, stream: PCM)
    ChatSvc->>ContextBuilder: build_context(user_123, profile)
    ContextBuilder-->>ChatSvc: student_context (OBC -> GOBCS, 89.5%, Pune)
    ChatSvc->>DB: add_message(user_123, role="user", content=query)
    ChatSvc->>Orch: answer(query, student_context)
    Orch-->>ChatSvc: Grounded shortlist & feasibility analysis
    ChatSvc->>DB: add_message(user_123, role="assistant", content=response)
    ChatSvc-->>Router: JSON {message, student_context_applied: true, personalized_for: "Aarav"}
    Router-->>Browser: HTTP 200 OK
    Browser->>Student: Displays personalized response with 🎯 badge
```

---

## 5. Security & Isolation Invariants

- **Token Tampering**: Any modification to the token header or payload causes immediate cryptographic verification failure in `JwtTokenProvider.decode_token()`.
- **Cross-Tenant Guard**: Every endpoint that accesses a user resource (`/api/onboarding/profile/{user_id}`, `/api/chat/history/{user_id}`) checks:
  $$\text{assert } \text{claim.sub} == \text{route.user\_id} \quad (\text{else } 403 \text{ Forbidden})$$
- **Password Hashes**: Plaintext passwords are never saved. Salted PBKDF2-HMAC-SHA256 digests are compared using constant-time string comparison (`hmac.compare_digest`).
