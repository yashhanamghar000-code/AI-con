"""
CollegeInfoAgent: semantic search over the vector index built by
build_vector_index.py. Used for free-text questions (affiliation, location,
"tell me about X") where exact-field cutoff lookup doesn't apply.

Every result carries its source chunk's metadata so the caller can cite it.
This agent never strips off citations or invents missing fields.
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional, Union


def ensure_chroma_embedding_function(ef: Any) -> Any:
    """Ensure a custom embedding function satisfies ChromaDB's EmbeddingFunction protocol."""
    if ef is None:
        return None
    if not hasattr(ef, "name"):
        name_str = getattr(ef, "__class__").__name__.lower()
        setattr(ef, "name", lambda: name_str)
    if not hasattr(ef, "default_space"):
        setattr(ef, "default_space", lambda: "cosine")
    if not hasattr(ef, "supported_spaces"):
        setattr(ef, "supported_spaces", lambda: ["cosine", "l2", "ip"])
    if not hasattr(ef, "get_config"):
        setattr(ef, "get_config", lambda: {})
    if not hasattr(ef, "build_from_config"):
        setattr(ef, "build_from_config", lambda cfg: ef)
    return ef


class CollegeInfoAgent:
    def __init__(
        self,
        vector_index_path: Union[str, Any],
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_function: Any = None,
    ):
        try:
            import chromadb
        except ImportError:
            raise SystemExit(
                "Missing dependency: chromadb.\n"
                "From the model_rag_agent_plan folder run:\n"
                "  pip install -r requirements.txt"
            )
        if embedding_function is not None:
            embedding_function = ensure_chroma_embedding_function(embedding_function)
        else:
            try:
                from chromadb.utils import embedding_functions
                embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model)
            except ImportError:
                raise SystemExit(
                    "Missing dependency: sentence-transformers.\n"
                    "From the model_rag_agent_plan folder run:\n"
                    "  pip install -r requirements.txt"
                )
        client = chromadb.PersistentClient(path=str(vector_index_path))
        self.collection = client.get_or_create_collection("college_info", embedding_function=embedding_function)

    def list_name_index(self) -> Dict[str, Dict[str, Optional[str]]]:
        """institute_name -> {institute_code?, record_id?} from indexed metadata."""
        data = self.collection.get(include=["metadatas"])
        index: Dict[str, Dict[str, Optional[str]]] = {}
        for meta in data.get("metadatas") or []:
            if not meta:
                continue
            name = (meta.get("institute_name") or "").strip()
            if not name:
                continue
            entry = index.setdefault(name, {})
            record_id = (meta.get("record_id") or "").strip()
            code = (meta.get("institute_code") or "").strip()
            if record_id:
                entry["record_id"] = record_id
            if code:
                entry["institute_code"] = code
        return index

    def search(
        self,
        query: str,
        institute_code: Optional[str] = None,
        record_id: Optional[str] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search the collection for relevant passages with optional college filter."""
        count = self.collection.count()
        if count == 0:
            return []
        n_results = max(1, min(n_results, count))

        where: Optional[Dict[str, Any]] = None
        if record_id:
            where = {"record_id": str(record_id)}
        elif institute_code:
            code_str = str(institute_code)
            where = {"institute_code": code_str}

        try:
            res = self.collection.query(query_texts=[query], n_results=n_results, where=where)
        except Exception:
            # Fallback if where filter finds no match
            if where:
                return []
            raise

        out: List[Dict[str, Any]] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0] if res.get("distances") else [None] * len(ids)

        for i, d, m, dist in zip(ids, docs, metas, dists):
            out.append({"chunk_id": i, "text": d, "metadata": m or {}, "distance": dist})
        return out

    def get_by_record_id(self, record_id: str) -> List[Dict[str, Any]]:
        """Directly retrieve all chunks indexed for a specific record_id without embedding similarity."""
        data = self.collection.get(where={"record_id": str(record_id)}, include=["documents", "metadatas"])
        out: List[Dict[str, Any]] = []
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        for i, d, m in zip(ids, docs, metas):
            out.append({"chunk_id": i, "text": d, "metadata": m or {}, "distance": None})
        return out

    def as_evidence_text(self, results: List[Dict[str, Any]]) -> str:
        """Format retrieval results into structured, citable evidence text."""
        if not results:
            return "No relevant information found in the college dataset."
        lines: List[str] = []
        for r in results:
            m = r.get("metadata") or {}
            ident = m.get("record_id") or m.get("institute_code") or "unknown"
            source = m.get("source_page") or "college profile"
            chunk_type = m.get("chunk_type") or "passage"
            lines.append(
                f"[{ident}:{r['chunk_id']}] ({chunk_type}, source: {source}):\n{r['text']}"
            )
        return "\n\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Quick manual test of CollegeInfoAgent")
    ap.add_argument("--vector-index", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--institute-code", default=None)
    ap.add_argument("--record-id", default=None)
    args = ap.parse_args()

    agent = CollegeInfoAgent(args.vector_index)
    results = agent.search(args.query, institute_code=args.institute_code, record_id=args.record_id)
    print(agent.as_evidence_text(results))
