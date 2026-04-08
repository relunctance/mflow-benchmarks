# Bug: `williolw23` Typo in Judge Prompt

## Location
`zep_locomo_eval.py`, line 26 (original script from getzep/zep-papers)

## Description
The ACCURACY_PROMPT contains a typo: `"You williolw23 be given"` instead of `"You will be given"`.

## Impact
Minimal — the LLM can still understand the instruction despite the typo. But it is sent to the judge LLM for every evaluation call.

## Why Not Fixed
Zep's official 75.13% was scored using this exact prompt. Fixing it would change the judge behavior and make results non-comparable.
