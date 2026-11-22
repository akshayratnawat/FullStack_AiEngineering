"""Split one filing's Markdown into chunks sized for the embedding model.

Docling parses the Markdown into a structured document (headings, paragraphs,
tables); its HybridChunker then splits along that structure and by token count.
No network calls happen here, so it is cheap to test.
"""

from dataclasses import dataclass
from io import BytesIO

import tiktoken
from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer

# text-embedding-3-small uses the cl100k_base tokenizer, so counts here are exact.
# It accepts 8,191 tokens per input; 512 keeps passages small enough to cite and to
# fit several in one LLM prompt.
EMBEDDING_ENCODING = "cl100k_base"
MAX_CHUNK_TOKENS = 512


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    content: str  # headings + text: exactly what is embedded and keyword-indexed
    section: str | None  # deepest heading, e.g. "Item 1A. Risk Factors"
    headings: list[str]  # full path, e.g. ["PART I", "Item 1A. Risk Factors"]
    token_count: int


class _MarkdownTablesProvider(ChunkingSerializerProvider):
    """Docling writes tables as `row, column = value` triplets by default, which
    repeats every label. Markdown tables are far more compact and readable."""

    def get_serializer(self, doc):
        return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())


def _make_chunker() -> tuple[HybridChunker, OpenAITokenizer]:
    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.get_encoding(EMBEDDING_ENCODING), max_tokens=MAX_CHUNK_TOKENS
    )
    return HybridChunker(tokenizer=tokenizer, serializer_provider=_MarkdownTablesProvider()), tokenizer


def chunk_markdown(markdown: str, name: str = "filing.md") -> list[Chunk]:
    """Chunk one Markdown document. Every chunk is at most MAX_CHUNK_TOKENS tokens."""
    stream = DocumentStream(name=name, stream=BytesIO(markdown.encode("utf-8")))
    document = DocumentConverter().convert(stream).document
    chunker, tokenizer = _make_chunker()

    chunks = []
    for raw in chunker.chunk(document):
        text = chunker.contextualize(raw)
        headings = list(raw.meta.headings or [])
        chunks.append(
            Chunk(
                chunk_index=len(chunks),
                content=text,
                section=headings[-1] if headings else None,
                headings=headings,
                token_count=tokenizer.count_tokens(text),
            )
        )
    return chunks
