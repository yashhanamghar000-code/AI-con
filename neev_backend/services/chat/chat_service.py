# -*- coding: utf-8 -*-
"""
Chat Domain Service.
Coordinates user queries, student context resolution, agent reasoning, and multi-tenant persistence.
Depends on abstractions (IChatRepository, IProfileRepository, IUserRepository, ITokenProvider, IContextBuilder).
"""

from typing import Dict, Any, Optional
from neev_backend.core.interfaces.repository_interface import IChatRepository, IProfileRepository, IUserRepository
from neev_backend.core.interfaces.auth_interface import ITokenProvider
from neev_backend.core.interfaces.chat_interface import IContextBuilder


# Module-level shortlist cache for PDF exports across student sessions
USER_SHORTLIST_CACHE: Dict[str, Dict[str, Any]] = {}

class ChatService:
    """Manages conversational student interactions with evidence-grounded AI reasoning."""

    def __init__(
        self,
        chat_repo: IChatRepository,
        profile_repo: IProfileRepository,
        user_repo: IUserRepository,
        token_provider: ITokenProvider,
        context_builder: IContextBuilder,
        orchestrator=None
    ):
        self.chat_repo = chat_repo
        self.profile_repo = profile_repo
        self.user_repo = user_repo
        self.token_provider = token_provider
        self.context_builder = context_builder
        self._orchestrator = orchestrator

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            try:
                from pathlib import Path
                from scripts.agents.orchestrator import Orchestrator
                from scripts.agents.cutoff_agent import CutoffAgent
                from scripts.agents.college_info_agent import CollegeInfoAgent
                
                base_dir = Path(__file__).resolve().parent.parent.parent.parent
                cutoffs_dir = base_dir / "cutoffs" / "phase3_final_staging"
                vector_index_dir = base_dir / "vector_index"
                
                cutoff_ag = CutoffAgent(cutoffs_dir) if cutoffs_dir.is_dir() else CutoffAgent()
                college_ag = None
                if vector_index_dir.is_dir():
                    try:
                        snap_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots"
                        local_model = "sentence-transformers/all-MiniLM-L6-v2"
                        if snap_dir.is_dir():
                            for s in snap_dir.iterdir():
                                if s.is_dir():
                                    local_model = str(s)
                                    break
                        college_ag = CollegeInfoAgent(vector_index_dir, model=local_model)
                    except Exception:
                        pass
                llm_call = None
                try:
                    import urllib.request
                    req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
                    with urllib.request.urlopen(req, timeout=0.8) as resp:
                        if resp.status == 200:
                            from scripts.rag_pipeline import call_llm
                            llm_call = lambda sys_p, usr_p: call_llm(sys_p, usr_p, model="qwen2.5:7b")
                except Exception:
                    llm_call = None

                self._orchestrator = Orchestrator(cutoff_ag, college_ag, llm_call=llm_call)
            except Exception as e:
                print(f"[Warning] Orchestrator initialization: {e}")
        return self._orchestrator

    def answer_query(
        self,
        query: str,
        user_id: str,
        raw_token: Optional[str] = None
    ) -> Dict[str, Any]:
        clean_query = query.strip()
        effective_uid = user_id or "guest"
        student_context = None

        # Resolve authenticated student context if token is present
        if raw_token:
            try:
                payload = self.token_provider.decode_token(raw_token)
                effective_uid = payload["sub"]
                profile = self.profile_repo.get_by_user_id(effective_uid)
                user_rec = self.user_repo.get_by_id(effective_uid)
                if profile:
                    student_context = self.context_builder.build_context(
                        user_id=effective_uid,
                        profile=profile,
                        user_record=user_rec
                    )
            except Exception:
                pass

        # 1. Save user query strictly partitioned by effective_uid
        self.chat_repo.add_message(user_id=effective_uid, role="user", content=clean_query)

        # 2. Process query via Orchestrator
        status_val = "answered"
        matched_college = None
        evidence = ""
        display_text = "I am ready to help you analyze college cutoffs, admissions rules, and career streams."
        total_matches = 0
        candidates = []
        intent = "info"
        query_type = "single_college"

        if self.orchestrator:
            try:
                res = self.orchestrator.answer(clean_query, student_context=student_context)
                status_val = res.get("status", "answered")
                matched_college = res.get("matched_college")
                evidence = res.get("evidence", "")
                message = res.get("message", "")
                total_matches = res.get("total_matches", 0)
                candidates = res.get("candidates", [])
                intent = res.get("intent", "info")
                query_type = res.get("query_type", "single_college")
                llm_answer = res.get("answer")

                if message and not llm_answer:
                    display_text = message
                elif llm_answer:
                    display_text = llm_answer
                elif evidence:
                    display_text = f"Here is the verified information for your query:\n\n{evidence}"
                else:
                    display_text = "I could not locate specific historical records matching those exact parameters. Please try refining your college name, category, or branch."
            except Exception as e:
                status_val = "error"
                display_text = f"An issue occurred while processing your request: {str(e)}"

        offer_pdf = False
        shortlist_data = []
        if isinstance(res, dict):
            offer_pdf = bool(res.get("offer_pdf", False))
            shortlist_data = res.get("shortlist", [])

        if offer_pdf or shortlist_data:
            USER_SHORTLIST_CACHE[effective_uid] = {
                "shortlist": shortlist_data,
                "query": clean_query,
                "user_context": student_context or {"user_id": effective_uid}
            }

        # 3. Save assistant response strictly partitioned by effective_uid
        self.chat_repo.add_message(
            user_id=effective_uid,
            role="assistant",
            content=display_text,
            status=status_val,
            matched_college=matched_college,
            evidence=evidence
        )

        return {
            "success": True,
            "status": status_val,
            "intent": intent,
            "query_type": query_type,
            "matched_college": matched_college,
            "total_matches": total_matches,
            "candidates": candidates,
            "message": display_text,
            "raw_evidence": evidence,
            "offer_pdf": offer_pdf,
            "pdf_url": f"/api/chat/pdf/{effective_uid}" if offer_pdf else None,
            "shortlist": shortlist_data,
            "student_context_applied": bool(student_context),
            "personalized_for": student_context.get("name") if student_context else None
        }

    def get_shortlist_pdf(self, user_id: str) -> Optional[bytes]:
        entry = USER_SHORTLIST_CACHE.get(user_id)
        if not entry or not entry.get("shortlist"):
            if self.orchestrator and getattr(self.orchestrator, "_conv_context", {}).get("last_shortlist"):
                entry = {
                    "shortlist": self.orchestrator._conv_context["last_shortlist"],
                    "query": "College Shortlist Report",
                    "user_context": {
                        "location": self.orchestrator._conv_context.get("location"),
                        "category": self.orchestrator._conv_context.get("category"),
                        "percentile": self.orchestrator._conv_context.get("percentile"),
                        "preferred_branches": self.orchestrator._conv_context.get("preferred_branches"),
                    }
                }
            else:
                return None
        try:
            from scripts.pdf_generator import generate_college_list_pdf
            return generate_college_list_pdf(
                query_title=entry.get("query", "College Shortlist Report"),
                colleges=entry["shortlist"],
                user_context=entry.get("user_context")
            )
        except Exception as e:
            print(f"[PDF Generation Error] {e}")
            return None

    def get_user_history(self, user_id: str, authenticated_uid: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        if authenticated_uid and user_id != authenticated_uid:
            from neev_backend.core.exceptions import AuthorizationError
            raise AuthorizationError("Access denied. You cannot view another student's conversation history.")

        history = self.chat_repo.get_history(user_id=user_id, limit=limit)
        return {
            "success": True,
            "user_id": user_id,
            "total_messages": len(history),
            "history": history
        }
