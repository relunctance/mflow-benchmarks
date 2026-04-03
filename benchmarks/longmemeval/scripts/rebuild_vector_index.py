#!/usr/bin/env python3
"""
Vector Index Rebuild Script - Fix empty index caused by embedding dimension mismatch

Root Cause:
- litellm.aembedding was not passed dimensions parameter during ingestion
- OpenAI text-embedding-3-small returns 1536 dimensions by default
- LanceDB table schema restricts to 1024 dimensions
- Validation failure caused all vectors to be skipped

Solution:
- Read nodes from each dataset's Kuzu graph database
- Use fixed embedding engine (now correctly passes dimensions=1024)
- Rewrite to LanceDB
"""

import os
import sys
from pathlib import Path

# Ensure running from correct directory
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

sys.path.insert(0, str(MFLOW_ROOT))

import asyncio
import argparse
import json
import kuzu
import lancedb
from datetime import datetime
from typing import Any, Optional
from uuid import UUID


async def get_all_datasets():
    """Get all datasets starting with lme_"""
    from m_flow.data.methods import get_datasets
    from m_flow.auth.methods import get_default_user
    
    user = await get_default_user()
    all_ds = await get_datasets(user.id)
    
    # Filter datasets starting with lme_
    lme_datasets = [ds for ds in all_ds if ds.name.startswith('lme_')]
    return lme_datasets


async def get_user_database_path():
    """Get current user's database path"""
    from m_flow.auth.methods import get_default_user
    
    user = await get_default_user()
    user_id = str(user.id)
    base_path = MFLOW_ROOT / 'm_flow' / '.m_flow_system' / 'databases' / user_id
    return base_path


def read_nodes_from_kuzu(dataset_id: str, user_db_path: Path) -> list:
    """Read all nodes from dataset's Kuzu graph database"""
    # Kuzu database filename format
    db_path = user_db_path / f"{dataset_id}.pkl"
    
    if not db_path.exists():
        print(f"  Warning: Kuzu database not found at {db_path}")
        return []
    
    try:
        db = kuzu.Database(str(db_path), read_only=True)
        conn = kuzu.Connection(db)
        
        # Query all nodes
        result = conn.execute("MATCH (n:Node) RETURN n")
        
        nodes = []
        while result.has_next():
            row = result.get_next()
            if row:
                nodes.append(row[0])
        
        return nodes
    except Exception as e:
        print(f"  Error reading Kuzu database {dataset_id}: {e}")
        return []


def create_memory_node_from_kuzu(kuzu_node: dict) -> Optional[Any]:
    """Create MFlow MemoryNode from Kuzu node"""
    from m_flow.core.domain.models.Episode import Episode
    from m_flow.core.domain.models.Facet import Facet
    from m_flow.core.domain.models.FacetPoint import FacetPoint
    from m_flow.core.domain.models.Entity import Entity
    from m_flow.core.domain.models.EntityType import EntityType
    
    node_type = kuzu_node.get('type', 'Entity')
    node_id = kuzu_node.get('id', '')
    name = kuzu_node.get('name', '')
    
    # Parse properties JSON
    props_str = kuzu_node.get('properties', '{}')
    try:
        props = json.loads(props_str)
    except (json.JSONDecodeError, TypeError):
        props = {}
    
    metadata = props.get('metadata', {})
    index_fields = metadata.get('index_fields', [])
    
    # Only process node types with index_fields
    if not index_fields:
        return None
    
    # Create corresponding MemoryNode based on node type
    try:
        if node_type == 'Episode':
            summary = props.get('summary', '')
            if not summary:
                return None
            node = Episode(
                id=UUID(node_id) if node_id else None,
                name=name,
                summary=summary,
                metadata={"index_fields": ["summary"]}
            )
            return node
            
        elif node_type == 'Facet':
            search_text = props.get('search_text', '')
            anchor_text = props.get('anchor_text', '')
            if not search_text and not anchor_text:
                return None
            node = Facet(
                id=UUID(node_id) if node_id else None,
                name=name,
                search_text=search_text or name,
                anchor_text=anchor_text or search_text or name,
                metadata={"index_fields": ["search_text", "anchor_text"]}
            )
            return node
            
        elif node_type == 'FacetPoint':
            search_text = props.get('search_text', '')
            if not search_text:
                return None
            node = FacetPoint(
                id=UUID(node_id) if node_id else None,
                name=name,
                search_text=search_text,
                metadata={"index_fields": ["search_text"]}
            )
            return node
            
        elif node_type == 'Entity':
            canonical_name = props.get('canonical_name', name)
            if not name and not canonical_name:
                return None
            node = Entity(
                id=UUID(node_id) if node_id else None,
                name=name or canonical_name,
                canonical_name=canonical_name or name,
                metadata={"index_fields": ["name", "canonical_name"]}
            )
            return node
            
        elif node_type == 'EntityType':
            if not name:
                return None
            node = EntityType(
                id=UUID(node_id) if node_id else None,
                name=name,
                metadata={"index_fields": ["name"]}
            )
            return node
        
    except Exception as e:
        # Silently handle errors, only record statistics
        return None
    
    return None


async def rebuild_vectors_for_dataset(dataset_id: str, dataset_name: str, user_db_path: Path):
    """Rebuild vector index for a single dataset"""
    from m_flow.storage.index_memory_nodes import index_memory_nodes
    from m_flow.context_global_variables import set_database_global_context_variables
    from m_flow.data.methods import get_datasets_by_name
    from m_flow.auth.methods import get_default_user
    
    print(f"  Processing {dataset_name}...")
    
    # Set dataset context
    user = await get_default_user()
    datasets = await get_datasets_by_name(dataset_name, user.id)
    if datasets:
        ds = datasets[0]
        await set_database_global_context_variables(ds.id, ds.owner_id)
    
    # Read Kuzu nodes
    kuzu_nodes = read_nodes_from_kuzu(dataset_id, user_db_path)
    
    if not kuzu_nodes:
        print(f"  No nodes found in Kuzu database")
        return 0
    
    print(f"  Found {len(kuzu_nodes)} Kuzu nodes")
    
    # Convert to MemoryNode objects
    memory_nodes = []
    type_counts = {}
    
    for kuzu_node in kuzu_nodes:
        node = create_memory_node_from_kuzu(kuzu_node)
        if node:
            memory_nodes.append(node)
            node_type = type(node).__name__
            type_counts[node_type] = type_counts.get(node_type, 0) + 1
    
    print(f"  Created {len(memory_nodes)} memory nodes: {type_counts}")
    
    if not memory_nodes:
        print(f"  No valid memory nodes to index")
        return 0
    
    print(f"  Indexing {len(memory_nodes)} memory nodes...")
    
    try:
        await index_memory_nodes(memory_nodes)
        print(f"  Successfully indexed {len(memory_nodes)} nodes")
        return len(memory_nodes)
    except Exception as e:
        print(f"  Error indexing: {e}")
        import traceback
        traceback.print_exc()
        return 0


async def verify_lancedb_tables(user_db_path: Path, limit: int = 5):
    """Verify LanceDB table status"""
    if not user_db_path.exists():
        print(f"  Database path does not exist: {user_db_path}")
        return
    
    lance_dirs = [f for f in os.listdir(user_db_path) if f.endswith('.lance.db')][:limit]
    
    print("\n=== LanceDB Table Verification ===")
    non_empty_count = 0
    empty_count = 0
    
    for lance_dir in lance_dirs:
        db_path = user_db_path / lance_dir
        try:
            db = lancedb.connect(str(db_path))
            tables = db.table_names()
            
            total_rows = 0
            for tbl in tables:
                t = db.open_table(tbl)
                total_rows += len(t)
            
            if total_rows > 0:
                print(f"  ✓ {lance_dir[:30]}... -> {total_rows} rows")
                non_empty_count += 1
            else:
                print(f"  ✗ {lance_dir[:30]}... -> empty")
                empty_count += 1
        except Exception as e:
            print(f"  ? {lance_dir[:30]}... -> Error: {e}")
    
    print(f"\n  Statistics: {non_empty_count} non-empty, {empty_count} empty tables (checked {limit})")


async def main():
    parser = argparse.ArgumentParser(description='Rebuild MFlow vector index')
    parser.add_argument('--max-datasets', type=int, default=5, help='Maximum number of datasets to process')
    parser.add_argument('--verify-only', action='store_true', help='Only verify, do not rebuild')
    parser.add_argument('--dataset', type=str, help='Only process specified dataset name')
    args = parser.parse_args()
    
    print("=" * 60)
    print("MFlow Vector Index Rebuild Tool")
    print("=" * 60)
    print(f"Time: {datetime.now()}")
    print(f"MFlow Root: {MFLOW_ROOT}")
    
    # Verify fix has been applied
    print("\n=== Verifying embedding fix ===")
    embedding_file = MFLOW_ROOT / 'm_flow' / 'adapters' / 'vector' / 'embeddings' / 'LiteLLMEmbeddingEngine.py'
    with open(embedding_file) as f:
        content = f.read()
        if 'dimensions=self.dimensions' in content:
            print("✓ LiteLLMEmbeddingEngine fixed (dimensions parameter added)")
        else:
            print("✗ LiteLLMEmbeddingEngine not fixed! Please add dimensions parameter first")
            return
    
    # Get user database path
    user_db_path = await get_user_database_path()
    print(f"User database path: {user_db_path}")
    
    if args.verify_only:
        await verify_lancedb_tables(user_db_path, limit=10)
        return
    
    # Get datasets
    print("\n=== Getting datasets ===")
    datasets = await get_all_datasets()
    print(f"Found {len(datasets)} lme_ datasets")
    
    if args.dataset:
        datasets = [ds for ds in datasets if ds.name == args.dataset]
        if not datasets:
            print(f"Dataset not found: {args.dataset}")
            return
    
    # Rebuild vector index
    print(f"\n=== Rebuilding vector index (max {args.max_datasets} datasets) ===")
    total_nodes = 0
    processed = 0
    
    for ds in datasets[:args.max_datasets]:
        dataset_id = str(ds.id)
        
        nodes = await rebuild_vectors_for_dataset(dataset_id, ds.name, user_db_path)
        total_nodes += nodes
        processed += 1
        
        # Interval to avoid API rate limits
        await asyncio.sleep(1.0)
    
    print(f"\n=== Complete ===")
    print(f"Datasets processed: {processed}")
    print(f"Total indexed nodes: {total_nodes}")
    
    # Verify results
    await verify_lancedb_tables(user_db_path, limit=min(processed, 5))


if __name__ == "__main__":
    asyncio.run(main())
