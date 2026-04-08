# Bug: `blip_captions` Field Name Typo in Ingestion Script

## Location
`zep_locomo_ingestion.py`, line 59 (original script from getzep/zep-papers)

## Description
The ingestion script reads `msg.get('blip_captions')` (plural), but the LOCOMO dataset field is `blip_caption` (singular).

## Impact
**1,226 image descriptions are silently dropped** during ingestion. All `blip_caption` fields return `None`, so no image context is ever included in the ingested data.

## Why Not Fixed
Zep's official score of 75.13% was achieved WITH this bug. Fixing it would change the ingestion data and make results non-comparable to the official benchmark.

## Verification
```python
# In locomo10.json, the field is 'blip_caption' (singular)
>>> sum(1 for u in data for k,v in u['conversation'].items() 
...     if isinstance(v, list) for m in v if 'blip_caption' in m)
1226  # messages with image descriptions

# The script checks 'blip_captions' (plural) — never matches
>>> msg.get('blip_captions')  # always returns None
```
