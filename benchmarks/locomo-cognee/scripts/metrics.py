"""
Evaluation Metrics for Cognee LOCOMO Benchmark
Fully aligned with MFlow/Mem0 official implementation
"""

import json
import re
from typing import Dict

import nltk
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from openai import OpenAI

from prompts import ACCURACY_PROMPT

try:
    nltk.download("punkt", quiet=True)
    nltk.download("punkt_tab", quiet=True)
except Exception as e:
    print(f"Warning: NLTK download issue: {e}")


def calculate_bleu1(prediction: str, reference: str) -> float:
    """
    BLEU-1 score (unigram only).
    Aligned with Mem0's calculate_bleu_scores().
    """
    if not prediction or not reference:
        return 0.0

    try:
        pred_tokens = nltk.word_tokenize(prediction.lower())
        ref_tokens = [nltk.word_tokenize(reference.lower())]
    except Exception:
        pred_tokens = prediction.lower().split()
        ref_tokens = [reference.lower().split()]

    if len(pred_tokens) == 0:
        return 0.0

    smooth = SmoothingFunction().method1

    try:
        score = sentence_bleu(
            ref_tokens,
            pred_tokens,
            weights=(1, 0, 0, 0),
            smoothing_function=smooth,
        )
    except Exception:
        score = 0.0

    return score


def calculate_f1(prediction: str, reference: str) -> float:
    """
    F1 score based on token overlap.
    Aligned with Mem0's calculate_metrics().
    """
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

    if precision + recall == 0:
        return 0.0

    f1 = 2 * precision * recall / (precision + recall)
    return f1


def extract_json(text: str) -> str:
    """Extract JSON object from text response."""
    match = re.search(r'\{[^{}]*\}', text)
    if match:
        return match.group()
    return text


def evaluate_llm_judge(
    question: str,
    gold_answer: str,
    generated_answer: str,
    client: OpenAI = None,
    model: str = "gpt-4o-mini",
) -> int:
    """
    LLM judge for answer correctness.
    Aligned with Mem0's evaluate_llm_judge().

    Returns 1 if CORRECT, 0 if WRONG.
    """
    if client is None:
        client = OpenAI()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": ACCURACY_PROMPT.format(
                    question=question,
                    gold_answer=gold_answer,
                    generated_answer=generated_answer,
                ),
            }],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        result = json.loads(extract_json(response.choices[0].message.content))
        label = result.get("label", "WRONG").upper()
        return 1 if label == "CORRECT" else 0

    except Exception as e:
        print(f"LLM Judge error: {e}")
        return 0
