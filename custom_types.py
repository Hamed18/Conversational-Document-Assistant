import pydantic


class RAGChunkAndSrc(pydantic.BaseModel):
    chunks: list[str]
    source_id: str | None = None


class RAGUpsertResult(pydantic.BaseModel):
    ingested: int


class RAGSearchResult(pydantic.BaseModel):
    contexts: list[str]
    sources: list[str]
    context_chunks: list[dict] = []


class RAQQueryResult(pydantic.BaseModel):
    answer: str
    sources: list[str]
    num_contexts: int