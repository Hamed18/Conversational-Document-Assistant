import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

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

        self.client = QdrantClient(url=url, timeout=30, check_compatibility=False)
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
        sources = set()

        for r in results:
            payload = getattr(r, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            if text:
                contexts.append(text)
                sources.add(source)

        return {"contexts": contexts, "sources": list(sources)}