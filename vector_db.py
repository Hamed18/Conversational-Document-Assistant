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

    def upsert(self, ids, vectors, payloads):
        points = [
            PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i])
            for i in range(len(ids))
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

        for r in results:
            payload = getattr(r, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            page = payload.get("page")
            section = payload.get("section")

            if text:
                # Include page and section in contextual header for grounded LLM reasoning
                header_parts = [f"Source: {source}"]
                if page:
                    header_parts.append(f"Page: {page}")
                if section:
                    header_parts.append(f"Section: {section}")
                header_line = " | ".join(header_parts)
                contexts.append(f"[{header_line}]\n{text}")

                # Format human-readable citation label for UI
                citation_parts = [source]
                if page:
                    citation_parts.append(f"Page {page}")
                if section and section != f"Page {page}":
                    citation_parts.append(f"Section: {section}")
                citation_label = " • ".join(citation_parts)

                if citation_label not in seen_sources:
                    seen_sources.add(citation_label)
                    sources.append(citation_label)

        return {"contexts": contexts, "sources": sources}