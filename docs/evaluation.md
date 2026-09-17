# Evaluation plan

The synthetic demo and unit tests establish bounded behavior; they do not
establish incident-diagnosis accuracy. Before publication claims are made,
build an evaluation set of independently authored, synthetic or approved
anonymized incidents.

Each case should include evidence, a private answer key, expected observations,
expected evidence references, important missing information, and distractors.
Keep answer keys outside the configured evidence root and out of source control.

Report per model and prompt version:

- citation precision and recall;
- unsupported-claim and invalid-reference rates;
- structured-output, repair, and truncation rates;
- coverage and false-completion rates;
- cold and warm latency, token throughput, and resource use;
- analyst usefulness rating and known failure modes.

Do not describe synthetic smoke tests as proof of root-cause accuracy. Retain
the benchmark JSON, model digest, prompt/schema version, source hashes, and
application version with every evaluation run.

Run the current machine's synthetic evaluator with:

```sh
uv run python scripts/evaluate-synthetic.py --model qwen3.5:9b --output outputs/evaluation.json
```

This is a regression signal for the four synthetic cases, not a substitute for
independent real-incident validation.

The first recorded Mac run is in
`docs/evaluation-results/qwen3.5-9b-2026-09-17.json`: 2 of 4 cases met the
simple required-term checks, all 8 extraction calls completed, and no invalid
references were observed. The misses are retained as a limitation rather than
silently converted into a success claim.
