"""
Modal deployment for Mflow QA benchmark.

Supports both unified_triplet and episodic retrieval modes.
"""

import asyncio
import datetime
import os
from dataclasses import asdict
from pathlib import Path

import modal

from qa.qa_benchmark_m_flow import MflowConfig, QABenchmarkMflow
from modal_apps.modal_image import image

APP_NAME = "qa-benchmark-m_flow"
VOLUME_NAME = "qa-benchmarks"
BENCHMARK_NAME = "m_flow"
CORPUS_FILE = Path("benchmark_corpus.json")
QA_PAIRS_FILE = Path("benchmark_qa_pairs.json")


def _create_benchmark_folder(
    volume_name: str, benchmark_name: str, timestamp: str, qa_engine: str
) -> str:
    """Create benchmark folder structure and return the answers folder path."""
    benchmark_folder = f"/{volume_name}/{benchmark_name}_{qa_engine}_{timestamp}"
    answers_folder = f"{benchmark_folder}/answers"
    os.makedirs(answers_folder, exist_ok=True)
    return answers_folder


volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

app = modal.App(APP_NAME, image=image, secrets=[modal.Secret.from_dotenv()])


@app.function(
    volumes={f"/{VOLUME_NAME}": volume},
    timeout=3600,
    cpu=4,
    memory=16384,
)
def run_m_flow_benchmark(config_params: dict, dir_suffix: str):
    """Run the Mflow QA benchmark on Modal."""
    print("Received benchmark request for Mflow.")

    qa_engine = config_params.get("qa_engine", "unified_triplet")
    answers_folder = _create_benchmark_folder(VOLUME_NAME, BENCHMARK_NAME, dir_suffix, qa_engine)
    print(f"Created benchmark folder: {answers_folder}")

    config = MflowConfig(**config_params)

    benchmark = QABenchmarkMflow.from_jsons(
        corpus_file=f"/root/{CORPUS_FILE.name}",
        qa_pairs_file=f"/root/{QA_PAIRS_FILE.name}",
        config=config,
    )

    print(f"Starting benchmark for {benchmark.system_name}...")
    benchmark.run()
    print(f"Benchmark finished. Results saved to {config.results_file}")

    volume.commit()


@app.local_entrypoint()
async def main(
    runs: int = 1,
    corpus_limit: int = None,
    qa_limit: int = None,
    qa_engine: str = "unified_triplet",  # "unified_triplet" or "episodic"
    top_k: int = 10,
    system_prompt_path: str = "answer_simple_question_benchmark2.txt",
    episodic_display_mode: str = "summary",
    clean_start: bool = True,
    print_results: bool = True,
):
    """Trigger Mflow QA benchmark runs on Modal."""
    print(f"🚀 Launching {runs} Mflow QA benchmark run(s) on Modal with these parameters:")
    print(f"  - runs: {runs}")
    print(f"  - corpus_limit: {corpus_limit}")
    print(f"  - qa_limit: {qa_limit}")
    print(f"  - qa_engine: {qa_engine}")
    print(f"  - top_k: {top_k}")
    print(f"  - system_prompt_path: {system_prompt_path}")
    print(f"  - episodic_display_mode: {episodic_display_mode}")
    print(f"  - clean_start: {clean_start}")
    print(f"  - print_results: {print_results}")

    base_timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    config_params_list = []

    for run_num in range(runs):
        config = MflowConfig(
            corpus_limit=corpus_limit,
            qa_limit=qa_limit,
            qa_engine=qa_engine,
            top_k=top_k,
            system_prompt_path=system_prompt_path,
            episodic_display_mode=episodic_display_mode,
            clean_start=clean_start,
            print_results=print_results,
        )
        config_params = asdict(config)

        unique_filename = f"run_{run_num + 1:03d}.json"
        config_params["results_file"] = (
            f"/{VOLUME_NAME}/{BENCHMARK_NAME}_{qa_engine}_{base_timestamp}/answers/{unique_filename}"
        )

        config_params_list.append(config_params)

    for params in config_params_list:
        run_m_flow_benchmark.spawn(params, base_timestamp)

    print(f"✅ {runs} benchmark task(s) submitted successfully.")
