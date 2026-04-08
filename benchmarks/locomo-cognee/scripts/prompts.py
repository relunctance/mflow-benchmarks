"""
Prompts for Cognee LOCOMO Benchmark

Three prompt variants designed for different Cognee search types:
1. COGNEE_CHUNKS_PROMPT      — for CHUNKS search (raw conversation fragments)
2. COGNEE_GRAPH_PROMPT       — for GRAPH_COMPLETION with only_context=True
3. COGNEE_COMPLETION_PROMPT  — for GRAPH_COMPLETION full completion (Cognee's own LLM)

Design rationale documented inline. The ACCURACY_PROMPT (judge) is identical
to MFlow/Mem0 — it evaluates answers, not context, so no adaptation needed.
"""

# ============================================================
# 1. CHUNKS Prompt — Cognee 的纯向量检索
# ============================================================
#
# Context format: raw conversation text with embedded timestamps
#   "[May 08, 2023, 1:56 PM] Caroline: I just got back from Italy."
#
# Key challenges vs MFlow Episodes:
#   - Raw text is verbose; Episode summaries are concise
#   - Timestamps embedded in text, not structured metadata
#   - Contains conversational noise (greetings, fillers)
#   - Information may be scattered across multiple chunks
#
# Design choices:
#   - "conversation fragments" not "memories" — matches actual content type
#   - Explicit instruction to extract facts from dialogue
#   - Strong timestamp parsing guidance with example
#   - "Be concise (5-6 words)" aligned with MFlow and Mem0
#   - "combine evidence" rule handles cross-chunk reasoning
#
COGNEE_CHUNKS_PROMPT = """Answer the question using ONLY the conversation fragments below. Be concise (5-6 words). No explanation.

RULES:
- These are raw conversation excerpts between two speakers. Extract the relevant facts from their dialogue.
- Read ALL fragments before answering — the answer may require combining information from multiple fragments.
- Timestamps in brackets (e.g., [May 08, 2023, 1:56 PM]) indicate when the conversation took place.
  Use them to resolve relative time references: "last year" in a May 2023 conversation means 2022.
- If fragments contain conflicting information, prefer the more recent conversation.
- Ignore conversational filler (greetings, small talk). Focus on factual statements.
- Say "Unknown" only if no fragment contains relevant information.

Conversation fragments from {speaker_1} & {speaker_2}:

{context}

Question: {question}

Answer:"""


# ============================================================
# 2. GRAPH Prompt — Cognee 的图检索上下文 (only_context=True)
# ============================================================
#
# Context format: resolve_edges_to_text() output
#   "Nodes:\nNode: title\n__node_content_start__\ncontent\n__node_content_end__\n\n
#    Connections:\nNodeA --[relation]--> NodeB"
#
# Key advantages over CHUNKS:
#   - Structured: entities and relationships are explicit
#   - Relationships enable multi-hop reasoning (Cat 3 questions)
#   - Node content preserves original text for fact extraction
#
# Key challenges:
#   - Formatting artifacts (__node_content_start/end__)
#   - Relationship labels may be cryptic
#   - Time info buried inside node content, not in structure
#
# Design choices:
#   - Explain the Nodes/Connections structure to the LLM
#   - "Follow connections to find indirect answers" — leverages graph for multi-hop
#   - Same timestamp resolution rules as CHUNKS prompt
#   - Same answer format constraint
#
COGNEE_GRAPH_PROMPT = """Answer the question using ONLY the knowledge graph context below. Be concise (5-6 words). No explanation.

CONTEXT FORMAT:
- "Nodes" contain text excerpts from conversations between the two speakers.
- "Connections" show relationships: SourceNode --[relationship]--> TargetNode.
- Text between __node_content_start__ and __node_content_end__ is the actual content.

RULES:
- Read ALL nodes and connections before answering.
- Use connections to trace indirect relationships — the answer may require following a chain of connections.
- Timestamps in brackets (e.g., [May 08, 2023, 1:56 PM]) inside node content indicate conversation dates.
  Use them to resolve relative time references: "last year" in a May 2023 conversation means 2022.
- If nodes contain conflicting information, prefer content from more recent conversations.
- Say "Unknown" only if no node or connection contains relevant information.

Knowledge graph context for {speaker_1} & {speaker_2}:

{context}

Question: {question}

Answer:"""


# ============================================================
# 3. COMPLETION Prompt — Cognee 自己的 LLM 回答 (search_type=GRAPH_COMPLETION)
# ============================================================
#
# When using Cognee's built-in GRAPH_COMPLETION (not only_context),
# Cognee's own LLM generates the answer. We pass this as the system_prompt
# via the search API's systemPrompt parameter.
#
# This prompt needs to:
#   - Override Cognee's default "Be as brief as possible" system prompt
#   - Enforce the 5-6 word constraint for LOCOMO compatibility
#   - Add time resolution guidance that Cognee's default prompt lacks
#
COGNEE_COMPLETION_PROMPT = """You are answering questions about conversations between two people based on a knowledge graph.

RULES:
- Answer in 5-6 words maximum. No explanation.
- Use the provided graph context (nodes and connections) to find the answer.
- Pay attention to timestamps: dates in brackets indicate when conversations occurred.
  Resolve relative time references accordingly (e.g., "last year" relative to the conversation date).
- If information conflicts, prefer the most recent data.
- Say "Unknown" only if the graph contains no relevant information."""


# ============================================================
# Judge Prompt — 与 MFlow/Mem0 完全一致 (无需适配)
# ============================================================
#
# The judge evaluates (question, gold_answer, generated_answer) triples.
# It does not see the retrieval context, so no Cognee-specific adaptation needed.
# Using the exact Mem0 ACCURACY_PROMPT ensures evaluation fairness.
#
ACCURACY_PROMPT = """
Your task is to label an answer to a question as 'CORRECT' or 'WRONG'. You will be given the following data:
    (1) a question (posed by one user to another user), 
    (2) a 'gold' (ground truth) answer, 
    (3) a generated answer
which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other user based on their prior conversations.
The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer: A shell necklace
The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT. 

For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it's the same date.

Now it's time for the real question:
Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}

First, provide a short (one sentence) explanation of your reasoning, then finish with CORRECT or WRONG. 
Do NOT include both CORRECT and WRONG in your response, or it will break the evaluation script.

Just return the label CORRECT or WRONG in a json format with the key as "label".
"""
