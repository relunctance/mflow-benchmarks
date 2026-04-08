import os
import json
from collections import defaultdict
from time import time

import requests
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from zep_cloud.client import AsyncZep
from zep_cloud import Message, EntityEdge, EntityNode
from openai import AsyncOpenAI
import asyncio

TEMPLATE = """
FACTS and ENTITIES represent relevant context to the current conversation.

# These are the most relevant facts for the conversation along with the datetime of the event that the fact refers to.
If a fact mentions something happening a week ago, then the datetime will be the date time of last week and not the datetime
of when the fact was stated.
Timestamps in memories represent the actual time the event occurred, not the time the event was mentioned in a message.
    
<FACTS>
{facts}
</FACTS>

# These are the most relevant entities
# ENTITY_NAME: entity summary
<ENTITIES>
{entities}
</ENTITIES>
"""

def compose_search_context(edges: list[EntityEdge], nodes: list[EntityNode]) -> str:
    facts = [f'  - {edge.fact} (event_time: {edge.valid_at})' for edge in edges]
    entities = [f'  - {node.name}: {node.summary}' for node in nodes]
    return TEMPLATE.format(facts='\n'.join(facts), entities='\n'.join(entities))

MAX_RETRIES = 3

async def search_with_retry(zep, query, graph_id, scope, reranker, limit):
    for attempt in range(MAX_RETRIES):
        try:
            return await zep.graph.search(
                query=query, graph_id=graph_id,
                scope=scope, reranker=reranker, limit=limit)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * (attempt + 1)
                print(f"    Retry {attempt+1}/{MAX_RETRIES} in {wait}s: {e}", flush=True)
                await asyncio.sleep(wait)
            else:
                print(f"    FAILED after {MAX_RETRIES} retries: {e}", flush=True)
                return None


async def main():
    load_dotenv()

    zep = AsyncZep(api_key=os.getenv("ZEP_API_KEY"), base_url="https://api.getzep.com/api/v2")

    locomo_df = pd.read_json('data/locomo.json')

    num_users = 10
    os.makedirs("data", exist_ok=True)

    # Load existing progress
    progress_file = "data/zep_locomo_search_results.json"
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            zep_search_results = json.load(f)
        print(f"Resuming: {sum(len(v) for v in zep_search_results.values())} results loaded", flush=True)
    else:
        zep_search_results = {}

    total_queries = 0
    total_duration_ms = 0

    for group_idx in range(num_users):
        qa_set = locomo_df['qa'].iloc[group_idx]
        group_id = f"locomo_experiment_user_{group_idx}"
        expected_count = len([q for q in qa_set if q.get('category') != 5])

        if group_id in zep_search_results and len(zep_search_results[group_id]) == expected_count:
            print(f"[SKIP] {group_id}: {expected_count} results already done", flush=True)
            total_queries += expected_count
            continue

        print(f"Searching {group_id} ({expected_count} questions)...", flush=True)
        user_results = []

        for qa in qa_set:
            query = qa.get('question')
            if qa.get('category') == 5:
                continue

            start = time()

            # 方案C: edges=7, nodes=3 (对齐 M-flow top_k=10 的信息总量)
            nodes_result = await search_with_retry(zep, query, group_id, 'nodes', 'rrf', 3)
            edges_result = await search_with_retry(zep, query, group_id, 'edges', 'cross_encoder', 7)

            nodes = (nodes_result.nodes if nodes_result else []) or []
            edges = (edges_result.edges if edges_result else []) or []

            context = compose_search_context(edges, nodes)
            duration_ms = (time() - start) * 1000
            total_duration_ms += duration_ms
            total_queries += 1

            user_results.append({'context': context, 'duration_ms': duration_ms})

        zep_search_results[group_id] = user_results
        print(f"  Done: {len(user_results)} results, saving...", flush=True)

        with open(progress_file, "w") as f:
            json.dump(zep_search_results, f, indent=2)

    avg_ms = total_duration_ms / total_queries if total_queries else 0
    print(f"\nSearch complete: {total_queries} queries, avg latency: {avg_ms:.0f}ms", flush=True)
    print('Save search results', flush=True)


if __name__ == "__main__":
    asyncio.run(main())
