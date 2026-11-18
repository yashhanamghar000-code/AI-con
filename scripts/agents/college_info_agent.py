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
        self.vector_index_path = vector_index_path
        self.model_name = model
        self.embedding_function = embedding_function

        # Task 10: Load and verify index manifest if present
        self.manifest: Optional[Dict[str, Any]] = None
        try:
            import json
            from pathlib import Path
            manifest_path = Path(vector_index_path) / "index_manifest.json"
            if manifest_path.is_file():
                self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            self.manifest = None

    def check_model_compatibility(self) -> Tuple[bool, str]:
        """Verify query embedding model matches the model used during index construction."""
        if not self.manifest:
            return True, "No manifest found in vector index; compatibility could not be verified."
        indexed_model = self.manifest.get("model_name") or self.manifest.get("embedding_model")
        active_ef_name = getattr(self.embedding_function, "name", lambda: self.model_name)() if hasattr(self.embedding_function, "name") else self.model_name
        if indexed_model and (indexed_model == self.model_name or indexed_model == active_ef_name):
            return True, f"Compatible: query model '{active_ef_name}' matches index model '{indexed_model}'."
        return False, f"Embedding model mismatch: index built with '{indexed_model}', query using '{active_ef_name}'."

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
        chunk_type: Optional[str] = None,
        n_results: int = 5,
        relevance_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search the collection for relevant passages with optional college and chunk-type filters."""
        count = self.collection.count()
        if count == 0:
            return []
        n_results = max(1, min(n_results, count))

        conditions = []
        if record_id:
            conditions.append({"record_id": str(record_id)})
        if institute_code:
            conditions.append({"institute_code": str(institute_code)})
        if chunk_type:
            conditions.append({"chunk_type": str(chunk_type)})

        if len(conditions) == 1:
            where: Optional[Dict[str, Any]] = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}
        else:
            where = None

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
            sim = None
            if dist is not None:
                sim = max(0.0, min(1.0, 1.0 - (float(dist) / 2.0)))

            is_relevant = True
            if relevance_threshold is not None:
                if relevance_threshold <= 1.0 and sim is not None:
                    is_relevant = (sim >= relevance_threshold)
                elif dist is not None:
                    is_relevant = (dist <= relevance_threshold)

            out.append({
                "chunk_id": i,
                "text": d,
                "metadata": m or {},
                "distance": dist,
                "similarity_score": sim,
                "is_relevant": is_relevant,
            })
        return out

    def search_for_institutes(
        self,
        query: str,
        institute_codes: List[str],
        chunk_type: Optional[str] = None,
        n_results_per_code: int = 1,
        relevance_threshold: Optional[float] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Perform targeted qualitative retrieval specifically for candidate colleges from structured discovery."""
        results_by_code: Dict[str, List[Dict[str, Any]]] = {}
        for code in institute_codes:
            hits = self.search(
                query=query,
                institute_code=code,
                chunk_type=chunk_type,
                n_results=n_results_per_code,
                relevance_threshold=relevance_threshold,
            )
            if hits:
                results_by_code[str(code)] = hits
        return results_by_code

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
