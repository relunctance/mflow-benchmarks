"""
M-Flow QA Benchmark — supports both UnifiedTripletSearch and EpisodicRetriever.

Uses M-Flow's native add/memorize pipeline for ingestion and supports
multiple retriever backends for answer generation.
"""

import json
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
import m_flow

from .qa_benchmark_base import QABenchmarkRAG, QABenchmarkConfig

load_dotenv()


@dataclass
class MflowConfig(QABenchmarkConfig):
    """Configuration for Mflow QA benchmark."""

    # Retriever selection: "unified_triplet" or "episodic"
    qa_engine: str = "unified_triplet"

    # Common retriever parameters
    top_k: int = 10
    system_prompt_path: str = "answer_simple_question_benchmark2.txt"
    wide_search_top_k: int = 100

    # Episodic-specific: display_mode ("summary" or "detail")
    episodic_display_mode: str = "summary"

    # Ingestion parameters
    chunk_size: int = 1024
    # Ingestion mode: each doc is add+memorize individually.
    # Episode Routing sees all previously committed Episodes,
    # enabling maximum cross-document merging.

    # Clean slate on initialization
    clean_start: bool = True

    # Default results file
    results_file: str = "benchmark_m_flow_results.json"


class QABenchmarkMflow(QABenchmarkRAG):
    """Mflow implementation of QA benchmark.

    Supports two retrieval modes:
    - "unified_triplet": Uses UnifiedTripletSearch (fine_grained_triplet_search)
    - "episodic": Uses EpisodicRetriever (episodic_bundle_search)
    """

    def __init__(self, corpus, qa_pairs, config: MflowConfig):
        super().__init__(corpus, qa_pairs, config)
        self.config: MflowConfig = config
        self.retriever = None

    @classmethod
    def from_jsons(
        cls,
        corpus_file: str,
        qa_pairs_file: str,
        config: MflowConfig,
    ) -> "QABenchmarkMflow":
        """Create benchmark instance by loading data from JSON files."""
        print(f"Loading corpus from {corpus_file}...")
        with open(corpus_file, "r", encoding="utf-8") as f:
            corpus = json.load(f)

        print(f"Loading QA pairs from {qa_pairs_file}...")
        with open(qa_pairs_file, "r", encoding="utf-8") as f:
            qa_pairs = json.load(f)

        print(f"Loaded {len(corpus)} documents and {len(qa_pairs)} QA pairs")
        return cls(corpus, qa_pairs, config)

    async def initialize_rag(self) -> Any:
        """Initialize Mflow system: prune → sequential add+memorize → init retriever.

        Uses the standard mflow ingestion pattern: add each document then memorize
        per batch. This allows Episode Routing to see previously committed Episodes
        and merge related documents into the same Episode across batches.

        Follows the official pattern from examples/test_comprehensive_episodic.py.
        """
        if self.config.clean_start:
            print("Pruning mflow data and system...", flush=True)
            await m_flow.prune.prune_data()
            await m_flow.prune.prune_system(metadata=True)

        # Sequential per-doc ingestion: add 1 doc → memorize → next doc.
        # Each memorize commits the Episode to the graph, so the next doc's
        # Episode Routing can see it and merge if related.
        # This is the standard mflow pattern for maximum routing quality.
        total = len(self.corpus)
        print(f"Ingesting {total} documents (per-doc add+memorize)...", flush=True)

        for idx, doc in enumerate(self.corpus, 1):
            print(f"  [{idx}/{total}] add+memorize...", flush=True)
            await m_flow.add(doc)
            await m_flow.memorize(chunk_size=self.config.chunk_size)

        print("Ingestion complete.", flush=True)

        # Initialize retriever based on qa_engine selection
        self._init_retriever()

        print(
            f"Initialized Mflow with {self.config.qa_engine} retriever "
            f"(top_k={self.config.top_k})",
            flush=True,
        )
        return "m_flow_initialized"

    def _init_retriever(self) -> None:
        """Create the appropriate retriever instance."""
        engine = self.config.qa_engine

        if engine == "unified_triplet":
            from m_flow.retrieval.unified_triplet_search import UnifiedTripletSearch

            self.retriever = UnifiedTripletSearch(
                system_prompt_path=self.config.system_prompt_path,
                top_k=self.config.top_k,
                wide_search_top_k=self.config.wide_search_top_k,
            )

        elif engine == "episodic":
            from m_flow.retrieval.episodic_retriever import EpisodicRetriever
            from m_flow.retrieval.episodic import EpisodicConfig

            episodic_config = EpisodicConfig(
                top_k=self.config.top_k,
                wide_search_top_k=self.config.wide_search_top_k,
                display_mode=self.config.episodic_display_mode,
            )
            self.retriever = EpisodicRetriever(
                system_prompt_path=self.config.system_prompt_path,
                top_k=self.config.top_k,
                config=episodic_config,
            )

        else:
            raise ValueError(
                f"Unsupported qa_engine: '{engine}'. "
                f"Choose 'unified_triplet' or 'episodic'."
            )

    async def cleanup_rag(self) -> None:
        """Clean up resources."""
        pass

    async def insert_document(self, document: str, document_id: int) -> None:
        """Not used — corpus is loaded in bulk during initialize_rag."""
        pass

    async def load_corpus_to_rag(self) -> None:
        """Not used — corpus loading is done inside initialize_rag."""
        pass

    async def query_rag(self, question: str) -> str:
        """Query mflow using the configured retriever."""
        if not self.retriever:
            raise RuntimeError("Retriever not initialized. Call initialize_rag() first.")

        try:
            results = await self.retriever.get_completion(question)
            if results and len(results) > 0:
                return str(results[0])
            else:
                return "No relevant information found."
        except Exception as e:
            print(f"Error during retrieval: {e}")
            return f"Error: {str(e)}"

    @property
    def system_name(self) -> str:
        """Return system name."""
        return f"Mflow-{self.config.qa_engine}"


if __name__ == "__main__":
    config = MflowConfig(
        corpus_limit=5,
        qa_limit=3,
        qa_engine="unified_triplet",
        top_k=10,
        print_results=True,
        clean_start=True,
    )

    benchmark = QABenchmarkMflow.from_jsons(
        corpus_file="benchmark_corpus.json",
        qa_pairs_file="benchmark_qa_pairs.json",
        config=config,
    )

    results = benchmark.run()
