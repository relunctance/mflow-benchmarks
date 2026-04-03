#!/usr/bin/env python3
"""
MFlow LongMemEval QA Evaluation Script
"""

import os
import sys
from pathlib import Path

# Ensure running from correct directory, set env vars before importing MFlow modules
MFLOW_ROOT = Path(__file__).parent.parent.parent
os.chdir(MFLOW_ROOT)

# Manually load .env file (before importing any MFlow modules)
env_path = MFLOW_ROOT / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value

# Now add path and import
sys.path.insert(0, str(MFLOW_ROOT))

import asyncio
import argparse
import json
import time
from typing import Dict, List

from openai import OpenAI
import nltk
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu

# Download NLTK data
try:
    nltk.download("punkt", quiet=True)
    nltk.download("punkt_tab", quiet=True)
except Exception:
    pass

def find_data_file() -> Path:
    """Find LongMemEval data file, trying multiple possible locations"""
    possible_paths = [
        Path(os.environ.get('LONGMEMEVAL_DATA', '')) if os.environ.get('LONGMEMEVAL_DATA') else Path(),
        Path(__file__).parent.parent / "data" / "longmemeval_oracle.json",
        Path(__file__).parent / "data" / "longmemeval_oracle.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    raise FileNotFoundError(
        f"LongMemEval data file not found. Please set BENCHMARK_WORKSPACE environment variable or place data file at:\n"
        f"  - {possible_paths[1]}\n"
        f"  - {possible_paths[-1]}"
    )


DATA_PATH = find_data_file()

# Prompts
ANSWER_PROMPT = """You are an intelligent memory assistant. Answer the question based on the retrieved memories.

# INSTRUCTIONS:
1. Carefully analyze all provided memories
2. Pay attention to timestamps to determine temporal relationships
3. If memories contain contradictory information, prioritize the most recent
4. Answer should be concise (less than 6 words)

# Retrieved Memories:
{memories}

# Question: {question}

Answer:"""

JUDGE_PROMPT = """Label the answer as 'CORRECT' or 'WRONG'.

Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}

Be generous: if the answer captures the same meaning or time period, mark CORRECT.
Return JSON: {{"label": "CORRECT"}} or {{"label": "WRONG"}}"""


def load_questions(max_questions: int = 50) -> List[Dict]:
    """Load LongMemEval questions"""
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    return questions[:max_questions]


def calculate_bleu1(prediction: str, reference: str) -> float:
    """Calculate BLEU-1 score"""
    if not prediction or not reference:
        return 0.0
    try:
        pred_tokens = nltk.word_tokenize(prediction.lower())
        ref_tokens = [nltk.word_tokenize(reference.lower())]
    except (LookupError, TypeError):
        pred_tokens = prediction.lower().split()
        ref_tokens = [reference.lower().split()]
    
    if len(pred_tokens) == 0:
        return 0.0
    
    smooth = SmoothingFunction().method1
    try:
        return sentence_bleu(ref_tokens, pred_tokens, weights=(1, 0, 0, 0), smoothing_function=smooth)
    except (ValueError, ZeroDivisionError):
        return 0.0


def calculate_f1(prediction: str, reference: str) -> float:
    """Calculate F1 score"""
    if not prediction and not reference:
        return 1.0
    if not prediction or not reference:
        return 0.0
    
    def tokenize(text: str) -> set:
        text = str(text).lower()
        text = text.replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ")
        return set(text.split())
    
    pred_tokens = tokenize(prediction)
    ref_tokens = tokenize(reference)
    
    if len(pred_tokens) == 0 or len(ref_tokens) == 0:
        return 0.0
    
    common = pred_tokens & ref_tokens
    if len(common) == 0:
        return 0.0
    
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


def evaluate_llm_judge(question: str, gold: str, generated: str, client: OpenAI, model: str) -> int:
    """LLM judge for answer correctness"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": JUDGE_PROMPT.format(
                question=question, gold_answer=gold, generated_answer=generated
            )}],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        result = json.loads(response.choices[0].message.content)
        return 1 if result.get("label", "").upper() == "CORRECT" else 0
    except Exception as e:
        print(f"  LLM Judge error: {e}")
        return 0


async def retrieve_memories(question: str, question_id: str, top_k: int = 10) -> str:
    """Retrieve memories using MFlow"""
    from m_flow.retrieval.episodic_retriever import EpisodicRetriever
    from m_flow.retrieval.episodic import EpisodicConfig
    from m_flow.context_global_variables import (
        backend_access_control_enabled,
        set_database_global_context_variables,
    )
    from m_flow.data.methods import get_datasets_by_name
    from m_flow.auth.methods import get_default_user
    
    dataset_name = f"lme_{question_id}"
    
    try:
        # Set dataset context (required for multi-user mode)
        if backend_access_control_enabled():
            default_user = await get_default_user()
            datasets = await get_datasets_by_name(dataset_name, default_user.id)
            if datasets:
                dataset = datasets[0]
                await set_database_global_context_variables(dataset.id, dataset.owner_id)
            else:
                print(f"  Warning: Dataset '{dataset_name}' not found")
                return ""
        
        config = EpisodicConfig(
            top_k=top_k,
            wide_search_top_k=top_k * 3,
            display_mode="summary",
        )
        retriever = EpisodicRetriever(config=config)
        edges = await retriever.get_triplets(question)
        
        if not edges:
            return ""
        
        # Extract memory text (following search_aligned.py approach)
        memories = []
        seen_episodes = set()
        
        for edge in edges:
            # Check both nodes
            for node in (getattr(edge, 'node1', None), getattr(edge, 'node2', None)):
                if node is None:
                    continue
                attrs = getattr(node, 'attributes', {}) or {}
                if attrs.get("type") == "Episode":
                    node_id = str(getattr(node, 'id', ''))
                    if node_id in seen_episodes:
                        continue
                    seen_episodes.add(node_id)
                    
                    # Get Episode summary
                    summary = attrs.get("summary", "")
                    if summary:
                        memories.append(summary)
            
            # Also try to get edge name
            edge_name = getattr(edge, 'name', None)
            if edge_name and edge_name not in memories:
                memories.append(edge_name)
        
        return "\n\n".join(memories[:top_k]) if memories else ""
    except Exception as e:
        print(f"  MFlow retrieval error: {e}")
        return ""


async def generate_answer(memories: str, question: str, client: OpenAI, model: str) -> str:
    """Generate answer"""
    if not memories:
        return "No relevant information found"
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": ANSWER_PROMPT.format(
                memories=memories, question=question
            )}],
            temperature=0.0,
            max_tokens=50,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  Answer generation error: {e}")
        return "Error generating answer"


async def evaluate_single(
    question: Dict,
    question_idx: int,
    total: int,
    client: OpenAI,
    answer_model: str,
    judge_model: str,
) -> Dict:
    """Evaluate a single question"""
    question_id = question['question_id']
    q_text = question['question']
    gold_answer = question['answer']
    
    print(f"[{question_idx+1}/{total}] MFlow: {question_id}")
    
    start_time = time.time()
    
    # 1. Retrieval
    retrieval_start = time.time()
    memories = await retrieve_memories(q_text, question_id)
    retrieval_ms = (time.time() - retrieval_start) * 1000
    
    # 2. Generate answer
    generation_start = time.time()
    generated = await generate_answer(memories, q_text, client, answer_model)
    generation_ms = (time.time() - generation_start) * 1000
    
    # 3. Calculate metrics
    bleu = calculate_bleu1(generated, gold_answer)
    f1 = calculate_f1(generated, gold_answer)
    llm_score = evaluate_llm_judge(q_text, gold_answer, generated, client, judge_model)
    
    total_ms = (time.time() - start_time) * 1000
    
    print(f"  Answer: {generated[:50]}... | BLEU: {bleu:.3f}, F1: {f1:.3f}, LLM: {llm_score}")
    
    return {
        'question_id': question_id,
        'question': q_text,
        'gold_answer': gold_answer,
        'generated_answer': generated,
        'memories_count': len(memories.split('\n\n')) if memories else 0,
        'bleu_score': round(bleu, 4),
        'f1_score': round(f1, 4),
        'llm_score': llm_score,
        'retrieval_ms': round(retrieval_ms, 2),
        'generation_ms': round(generation_ms, 2),
        'total_ms': round(total_ms, 2),
    }


async def main():
    parser = argparse.ArgumentParser(description='MFlow LongMemEval QA Evaluation')
    parser.add_argument('--max-questions', type=int, default=50, help='Number of questions to evaluate')
    parser.add_argument('--answer-model', type=str, default='gpt-4.1-mini', help='Answer model')
    parser.add_argument('--judge-model', type=str, default='gpt-4.1-mini', help='Judge model')
    parser.add_argument('--output-dir', type=str, default='results', help='Output directory')
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"MFlow LongMemEval Evaluation")
    print(f"{'='*60}")
    print(f"EMBEDDING_DIMENSIONS: {os.environ.get('EMBEDDING_DIMENSIONS', 'NOT SET')}")
    print(f"{'='*60}")
    
    # Load questions
    questions = load_questions(args.max_questions)
    print(f"Loaded {len(questions)} questions")
    
    # OpenAI client
    client = OpenAI()
    
    # Evaluate each question
    results = []
    start_time = time.time()
    
    for idx, q in enumerate(questions):
        result = await evaluate_single(
            q, idx, len(questions),
            client, args.answer_model, args.judge_model
        )
        results.append(result)
        
        # Avoid API rate limiting
        await asyncio.sleep(0.5)
    
    total_time = time.time() - start_time
    
    # Calculate summary statistics
    n = len(results) if results else 1  # Avoid division by zero
    summary = {
        'engine': 'mflow',
        'total_questions': len(results),
        'answer_model': args.answer_model,
        'judge_model': args.judge_model,
        'avg_bleu': round(sum(r['bleu_score'] for r in results) / n, 4) if results else 0,
        'avg_f1': round(sum(r['f1_score'] for r in results) / n, 4) if results else 0,
        'llm_accuracy': round(sum(r['llm_score'] for r in results) / n, 4) if results else 0,
        'avg_retrieval_ms': round(sum(r['retrieval_ms'] for r in results) / n, 2) if results else 0,
        'avg_generation_ms': round(sum(r['generation_ms'] for r in results) / n, 2) if results else 0,
        'total_time_seconds': round(total_time, 2),
    }
    
    print(f"\n{'='*60}")
    print(f"MFlow Evaluation Complete")
    print(f"{'='*60}")
    print(f"BLEU-1: {summary['avg_bleu']:.4f}")
    print(f"F1: {summary['avg_f1']:.4f}")
    print(f"LLM-Judge Accuracy: {summary['llm_accuracy']:.4f}")
    print(f"Average retrieval latency: {summary['avg_retrieval_ms']:.2f}ms")
    print(f"Average generation latency: {summary['avg_generation_ms']:.2f}ms")
    print(f"Total time: {summary['total_time_seconds']:.2f}s")
    
    # Save results
    output_dir = MFLOW_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "mflow_eval_results.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'summary': summary, 'results': results}, f, indent=2, ensure_ascii=False)
    print(f"Results saved: {output_path}")


if __name__ == '__main__':
    asyncio.run(main())
