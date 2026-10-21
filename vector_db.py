import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue, FilterSelector

load_dotenv()


class QdrantStorage:
    def __init__(
        self,
        url: str | None = None,
        collection: str | None = None,
        dim: int | None = None,
    ):
        url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.collection = collection or os.getenv("QDRANT_COLLECTION", "docs")
        dim = dim or int(os.getenv("EMBED_DIM", "3072"))

        api_key = os.getenv("QDRANT_API_KEY")
        self.client = QdrantClient(url=url, api_key=api_key, timeout=30, check_compatibility=False)
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
        try:
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name="source",
                field_schema="keyword",
            )
        except Exception:
            pass

    def upsert(self, ids, vectors, payloads, batch_size: int = 50):
        """
        Upserts vectors into Qdrant Cloud in manageable batches
        to prevent large payload buffer spikes on memory-constrained servers.
        """
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_vecs = vectors[i : i + batch_size]
            batch_payloads = payloads[i : i + batch_size]
            points = [
                PointStruct(id=batch_ids[j], vector=batch_vecs[j], payload=batch_payloads[j])
                for j in range(len(batch_ids))
            ]
            self.client.upsert(self.collection, points=points)

    def delete_by_source(self, source_id: str):
        """Removes all indexed points matching the given source filename."""
        try:
            self.client.delete(
                collection_name=self.collection,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="source",
                                match=MatchValue(value=source_id),
                            )
                        ]
                    )
                ),
            )
        except Exception as e:
            print(f"Warning: Failed to delete points for {source_id} from Qdrant: {e}")

    def search(self, query_vector, top_k: int = 5):
        # Support modern qdrant query_points as well as search
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                with_payload=True,
                limit=top_k,
            )
            results = response.points
        else:
            results = self.client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                with_payload=True,
                limit=top_k,
            )

        contexts = []
        sources = []
        seen_sources = set()

        idx = 1
        for r in results:
            payload = getattr(r, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            page = payload.get("page")
            section = payload.get("section")

            if text:
                # Include numeric index, page, and section in contextual header for grounded LLM reasoning
                header_parts = [f"Source: {source}"]
                if page:
                    header_parts.append(f"Page: {page}")
                if section:
                    header_parts.append(f"Section: {section}")
                header_line = " | ".join(header_parts)
                contexts.append(f"[{idx}] {header_line}\n{text}")

                # Format human-readable citation label with matching numeric reference [idx]
                citation_parts = [source]
                if page:
                    citation_parts.append(f"Page {page}")
                if section and section != f"Page {page}":
                    citation_parts.append(f"Section: {section}")
                citation_label = f"[{idx}] " + " • ".join(citation_parts)

                if citation_label not in seen_sources:
                    seen_sources.add(citation_label)
                    sources.append(citation_label)

                idx += 1

        return {"contexts": contexts, "sources": sources}