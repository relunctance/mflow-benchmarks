# Dataset: LoCoMo-10

The LoCoMo-10 dataset is **not included** in this package due to its license. You must download it separately.

## Source

- **Repository**: [snap-research/locomo](https://github.com/snap-research/locomo)
- **Paper**: Maharana et al., "LoCoMo: Long-Context Conversation Memory", 2024
- **File**: `locomo10.json`

## Download

```bash
# Option 1: Direct download
curl -L -o dataset/locomo10.json \
  "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"

# Option 2: Clone the repo
git clone https://github.com/snap-research/locomo.git
cp locomo/data/locomo10.json dataset/
```

## Verification

The file should contain 10 conversation objects. Quick check:

```bash
python3 -c "import json; d=json.load(open('dataset/locomo10.json')); print(f'{len(d)} conversations, {sum(len(c[\"qa\"]) for c in d)} questions')"
# Expected: 10 conversations, 1986 questions
```

## Placement

Place the file at `dataset/locomo10.json` relative to the scripts directory:

```
cognee-locomo-bench/
├── dataset/
│   └── locomo10.json    ← place here
├── run_ingest.py
├── search_aligned.py
└── ...
```
