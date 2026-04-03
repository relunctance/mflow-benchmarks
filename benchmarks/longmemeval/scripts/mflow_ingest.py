#!/usr/bin/env python3
"""
MFlow LongMemEval Ingestion Script
Ingests data isolated by question, each question uses its own dataset_name
"""

import asyncio
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add MFlow project path
MFLOW_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(MFLOW_ROOT))

from dotenv import load_dotenv
load_dotenv(MFLOW_ROOT / '.env')

from m_flow import ContentType
import m_flow


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


def load_questions() -> list:
    """Load LongMemEval question data"""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Data file does not exist: {DATA_PATH}")
    
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    
    print(f"✓ Loaded {len(questions)} questions")
    return questions


def parse_date(date_str: str) -> datetime:
    """
    Parse LongMemEval date format: '2023/04/10 (Mon) 17:50'
    Returns datetime object in UTC timezone
    """
    return datetime.strptime(
        date_str + ' UTC', 
        '%Y/%m/%d (%a) %H:%M UTC'
    ).replace(tzinfo=timezone.utc)


def format_session(session: list, date_str: str) -> str:
    """
    Format session message list as text
    Includes timestamp information for temporal reasoning
    """
    lines = [f"[Session Date: {date_str}]"]
    for msg in session:
        role = msg['role'].upper()
        content = msg['content']
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


async def ingest_question(question: dict, question_idx: int, total: int) -> dict:
    """Ingest data for a single question"""
    question_id = question.get('question_id', f'q_{question_idx}')
    dataset_name = f"lme_{question_id}"
    
    sessions = question.get('haystack_sessions', [])
    dates = question.get('haystack_dates', [])
    
    if len(sessions) != len(dates):
        print(f"⚠️ Question {question_id}: sessions ({len(sessions)}) and dates ({len(dates)}) count mismatch")
        return {'question_id': question_id, 'status': 'error', 'error': 'length_mismatch'}
    
    total_messages = sum(len(s) for s in sessions)
    start_time = time.time()
    
    print(f"[{question_idx+1}/{total}] Ingesting question {question_id}: {len(sessions)} sessions, {total_messages} messages")
    
    try:
        # Ingest by session: add + memorize per session
        # This is MFlow's recommended pattern to ensure Episode Routing can see previously ingested Episodes
        for session_idx, session in enumerate(sessions):
            date_str = dates[session_idx]
            session_text = format_session(session, date_str)
            
            await m_flow.add(
                data=session_text,
                dataset_name=dataset_name,
                created_at=parse_date(date_str)
            )
            
            # Memorize each session individually to ensure Episode Routing works
            await m_flow.memorize(
                datasets=[dataset_name],
                content_type=ContentType.DIALOG
            )
        
        elapsed = time.time() - start_time
        print(f"  ✓ Complete ({elapsed:.1f}s)")
        
        return {
            'question_id': question_id,
            'status': 'success',
            'sessions': len(sessions),
            'messages': total_messages,
            'elapsed_seconds': elapsed
        }
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"  ✗ Failed: {e}")
        return {
            'question_id': question_id,
            'status': 'error',
            'error': str(e),
            'elapsed_seconds': elapsed
        }


async def main():
    parser = argparse.ArgumentParser(description='MFlow LongMemEval Ingestion Script')
    parser.add_argument('--max-questions', type=int, default=50, help='Maximum questions to process (default: 50)')
    parser.add_argument('--start-from', type=int, default=0, help='Start from Nth question (default: 0)')
    parser.add_argument('--verbose', action='store_true', help='Show verbose logs')
    args = parser.parse_args()
    
    print("=" * 60)
    print("MFlow LongMemEval Ingestion Script")
    print("=" * 60)
    print(f"MFlow Root: {MFLOW_ROOT}")
    print(f"Data Path: {DATA_PATH}")
    print(f"Processing Range: questions {args.start_from} - {args.start_from + args.max_questions - 1}")
    print("=" * 60)
    
    # Load data
    questions = load_questions()
    
    # Select processing range
    end_idx = min(args.start_from + args.max_questions, len(questions))
    questions_to_process = questions[args.start_from:end_idx]
    
    print(f"\nStarting ingestion of {len(questions_to_process)} questions...\n")
    
    results = []
    total_start = time.time()
    
    for idx, question in enumerate(questions_to_process):
        result = await ingest_question(question, args.start_from + idx, end_idx)
        results.append(result)
    
    total_elapsed = time.time() - total_start
    
    # Statistics
    success_count = sum(1 for r in results if r['status'] == 'success')
    error_count = sum(1 for r in results if r['status'] == 'error')
    total_messages = sum(r.get('messages', 0) for r in results if r['status'] == 'success')
    
    print("\n" + "=" * 60)
    print("Ingestion Complete")
    print("=" * 60)
    print(f"Success: {success_count}, Failed: {error_count}")
    print(f"Total messages: {total_messages}")
    print(f"Total time: {total_elapsed:.1f}s")
    if len(questions_to_process) > 0:
        print(f"Average: {total_elapsed/len(questions_to_process):.1f}s/question")
    
    # Save results
    result_file = Path(__file__).parent / f"mflow_ingest_results_{args.start_from}_{end_idx}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump({
            'start_idx': args.start_from,
            'end_idx': end_idx,
            'total_elapsed': total_elapsed,
            'success_count': success_count,
            'error_count': error_count,
            'results': results
        }, f, indent=2, ensure_ascii=False)
    print(f"Results saved: {result_file}")
    
    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
