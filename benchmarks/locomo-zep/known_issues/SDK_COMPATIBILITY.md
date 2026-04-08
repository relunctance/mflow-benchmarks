# Zep Cloud SDK Compatibility

## Problem
The original benchmark scripts (from `getzep/zep-papers`) were written for `zep-cloud` SDK version ~2.x. The SDK has since been updated to 3.x with breaking API changes.

## Breaking Changes in 3.x

| Feature | SDK 2.x | SDK 3.x |
|---------|---------|---------|
| Group management | `zep.group.add(group_id=)` | Removed entirely |
| Graph creation | N/A | `zep.graph.create(graph_id=)` |
| Graph add data | `graph.add(..., group_id=)` | `graph.add(..., graph_id=)` |
| Graph search | `graph.search(..., group_id=)` | `graph.search(..., graph_id=)` |
| Add created_at | `graph.add(..., created_at=)` | `graph.add(..., created_at=)` ✓ |

## Compatible Versions

- **Original scripts**: Require `zep-cloud==2.22.1` (last version with `group_id`)
- **Adapted scripts**: Require `zep-cloud>=3.0` (uses `graph_id`)

## Installation

```bash
# For original scripts
pip install 'zep-cloud==2.22.1'

# For adapted scripts
pip install 'zep-cloud>=3.0'
```
