import os
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer

app = FastAPI(title="SawtAI Encoders", version="0.2.0")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
MODEL_DEVICE = os.getenv("MODEL_DEVICE", "cuda")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    documents: list[str] = Field(min_length=1, max_length=40)


@lru_cache
def embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL, device=MODEL_DEVICE)


@lru_cache
def reranking_model() -> CrossEncoder:
    return CrossEncoder(RERANK_MODEL, device=MODEL_DEVICE)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "embedding_model": EMBEDDING_MODEL,
        "reranker_model": RERANK_MODEL,
        "device": MODEL_DEVICE,
    }


@app.post("/embed")
async def embed(payload: EmbedRequest) -> dict[str, object]:
    vectors = embedding_model().encode(
        payload.texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return {"model": EMBEDDING_MODEL, "dimension": int(vectors.shape[1]), "embeddings": vectors.tolist()}


@app.post("/rerank")
async def rerank(payload: RerankRequest) -> dict[str, object]:
    pairs = [(payload.query, document) for document in payload.documents]
    scores = reranking_model().predict(pairs)
    return {"model": RERANK_MODEL, "scores": [float(score) for score in scores]}
