# How MedAgentBench's potassium task is evaluated

MedAgentBench's potassium task asks an agent to check a patient's most recent potassium result and, if it is low, to submit two orders. A scripted baseline that reads only the first page of search results passes Stanford's grader on all 30 released instances of the task, although on 12 of them that page does not contain the patient's most recent result: on those 12, an older result leads to the same action. This repository derives 629 further instances from the benchmark's own records, all of which require the orders, and the same baseline passes 299 of them. The outcome expected on each derived instance comes from a Lean specification of the task's instruction, and Lean proved that the reference implementation meets that specification for every list of results.

**Read the page: [wcook04.github.io/medagentbench-reader](https://wcook04.github.io/medagentbench-reader/)**, or the same text typeset as a [33-page PDF](https://wcook04.github.io/medagentbench-reader/medagentbench-potassium-task.pdf), with an abstract, numbered tables and figures, the references and the glossary. This is a prototype. No one outside the study has reviewed it, and corrections are welcome as issues on this repository.

[MedAgentBench](https://doi.org/10.1056/AIdbp2500144) (Jiang and coauthors, Stanford) evaluates language-model agents on clinical tasks in a simulated electronic health record. Its potassium replacement task, task 9, has 30 instances, and on 29 of them Stanford's grader requires no order. This repository follows that one task from its instruction to its grading code. The page in `site/` reports the results, and every number on it is read from `results/*.json`.

## Main results

| | 30 released instances | 629 derived instances that require the orders |
|---|---|---|
| Null agent: sends no request and finishes with an empty answer | 29 | 0 |
| First-page baseline: reads only the first page of one search | 30 | 299 |
| All-results baseline: the same program, asking for every potassium result in one page | 30 | 629 |
| DeepSeek V4.1 Flash, server's default sort order | 30 | 255 |
| DeepSeek V4.1 Flash, most-recent-first sort order | not run | 521 |

Entries are instances passed. The three baselines are scored by Stanford's grader as released. The model is scored by the same grader after two changes to each run: an oral route written as an object is rewritten as a string, and the final answer is removed from scoring (the relaxed grader, below). As released, the grader passes none of the model's 2,506 runs.

The benchmark's record server returns search results 20 to a page, in order of record id, and the description of the search that the agent receives does not say so. In 12 of the model's 30 runs on the released instances, no server response contained the patient's most recent result.

Asked to write the whole task once as a Python program from the task text and the tool definitions, the model wrote 20 functions that all read only the first page of their search. 14 of them make the first-page baseline's decision, with the same dose, on every one of the 7,590 derived instances. After one revision, in which the model saw its own requests and the server's responses on a synthetic potassium history, 14 of the 20 pass on all 629 instances, and 1 does within the benchmark's limit of 8 rounds.

## What was done

1. **Specification.** The task's instruction is written as a formal specification in Lean, with a reference implementation and proofs that the implementation meets the specification for every list of results (`lean/Potassium.lean`).
2. **Derived instances.** The benchmark's records hold 7,702 potassium results for 100 patients. Setting the unchanged task at each distinct time a result was issued gives 7,590 derived instances. On 629 of them, in 59 patients, the most recent result is below 3.5 mmol/L and the two orders are required.
3. **Baselines.** A null agent, a first-page baseline and an all-results baseline are run through the benchmark's protocol and scored by Stanford's unmodified grader (`study/agent/baselines.py`).
4. **One model.** DeepSeek V4.1 Flash is run on all 629 with the benchmark's prompt, tools and task text unchanged: once with the server's default sort order, and once with one change to the server, so that a search lists the most recent results first.
5. **Two graders.** Each run is scored by Stanford's grader as released and by the relaxed grader: the same unmodified grader, applied after an oral route written as the object the tool definition declares has been rewritten as the string `oral` and the final answer has been replaced by an empty list, which removes it from scoring. `study/agent/audit.py` also records, for every run, which searches it made and whether any server response contained the patient's most recent result.
6. **Model-written programs.** The same model is asked to write the whole task once as a Python program, and each program is run on every derived instance (`study/whole_task.py`).

## What is in the repository

| Path | Contents |
|---|---|
| `lean/Potassium.lean` | The specification (`Spec`), the reference implementation (`run`) and the proofs. Lean 4.35.0, core library only. |
| `lean/Oracle.lean` | A command-line program that runs the reference implementation on input lines. |
| `lean/Creatinine.lean`, `lean/CrOracle.lean` | A second rule (a creatinine rise of at least 0.3 mg/dL within 48 hours), specified and proved the same way. Not discussed on the page. |
| `study/extract.py` | Reads potassium and creatinine results from a local copy of the benchmark's record server into a private file. |
| `study/apply_rule.py` | Runs the reference implementation on every derived instance and writes counts to `results/potassium_rule.json`. |
| `study/grader_controls.py` | Runs Stanford's task 9 grader on hand-written submissions over synthetic results. |
| `study/agent/standin.py` | The mock server: rebuilds potassium histories at earlier times and serves them from memory in the record server's search format. Its `conformance` command compares it with the released server. |
| `study/agent/baselines.py` | The null agent, the first-page baseline and the all-results baseline, run through the protocol and scored by Stanford's grader. |
| `study/agent/run_standin.py` | Runs the benchmark's protocol on a hosted model against the mock server. |
| `study/agent/analyse.py` | Scores the stored runs with Stanford's grader, as released and relaxed. |
| `study/agent/audit.py` | The per-run audit, the paired comparisons, the patient-level intervals and the six runs shown step by step on the page. |
| `study/whole_task.py` | Asks the model for a program that does the whole task with the agent's tools, and scores each program on every derived instance. |
| `study/programs.py` | An earlier experiment, not on the page: the model writes the dose calculation alone as a Python function, and each function is compared with the reference implementation. |
| `results/` | Aggregate results. `results/runs_table.csv` has one row per model run in the main conditions, with its searches, its verdicts and its class in the error analysis, and no patient values. `results/whole_task_programs/` and `results/programs/` hold the model-written programs, unedited. |
| `site/` | The page and its build script, `site/build.py`. `site/make_pdf.py` typesets the page's text as `site/medagentbench-potassium-task.pdf`: Chromium saves each figure as an image, Pandoc converts the article to LaTeX with `site/paper_preamble.tex`, and Tectonic sets the PDF. |

## What is not in the repository

- **Patient records.** The records are de-identified patient data that Stanford distributes inside the benchmark's Docker image. The scripts read a private extract whose path you pass on the command line. The one exception is `results/worked_examples.json`: six runs shown step by step on the page, each with one patient's potassium values on one instance, with the patient identifier replaced and every time shifted.
- **Stanford's grader.** The benchmark's README links to it. The scripts take its path and run it unmodified. The copy used has SHA-256 `67d19da263ac92c1b7075b3218ace3a4bd19b206a06fc7aebcc897dc39625419`.
- **Full transcripts.** They contain record text and stay in a private folder.

## Reproducing

Build the Lean files, which checks the proofs:

```bash
cd lean && lake build && lake build oracle
```

With the benchmark's record server running locally and its repository checked out:

```bash
python3 study/extract.py --bench /path/to/MedAgentBench --out PRIVATE/records.json
python3 study/apply_rule.py --records PRIVATE/records.json --out results/potassium_rule.json
python3 study/grader_controls.py --grader /path/to/refsol.py --out results/grader_controls.json
python3 study/agent/standin.py fetch --records PRIVATE/records.json --out PRIVATE/agent/k_resources.json
python3 study/agent/standin.py cases --resources PRIVATE/agent/k_resources.json --out PRIVATE/agent/cases2.json
python3 study/agent/standin.py conformance --resources PRIVATE/agent/k_resources.json --patients 100 --out results/standin_conformance.json
python3 study/agent/baselines.py --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json --out results/baselines.json
python3 study/agent/analyse.py --runs PRIVATE/agent/runs --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json --out results/agent_runs.json
python3 study/agent/audit.py --runs PRIVATE/agent/runs --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json --out results/audit.json --examples results/worked_examples.json --table results/runs_table.csv
python3 study/whole_task.py check --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json
python3 site/build.py
```

The scripts find the benchmark checkout and the grader file through `MEDAGENTBENCH_REPO` and `MEDAGENTBENCH_GRADER` (see `study/local_paths.py`). The model runs (`study/agent/run_standin.py`, `study/whole_task.py generate`) call a hosted model through OpenRouter and need an API key in `OPENROUTER_API_KEY`. Model runs vary between repeats, so a rerun will not reproduce the stored runs exactly.

## Limits

- One model was run, DeepSeek V4.1 Flash at low reasoning effort, once per instance and condition. Repeating 100 instances changed the pass or fail result on 16.
- The 629 instances come from 59 patients, and five patients supply 275 of them. They were kept because the orders are required, and they are rebuilt from the final version of each result. The page gives confidence intervals that resample patients, and the patient-level mean of the pass rates.
- The mock server is not Stanford's server software. `results/standin_conformance.json` compares the two on 2,200 searches for the 100 real patients: 2,191 are identical, and the 9 differences are all in sorted searches.
- The relaxed grader is a choice. It changes the form of the route and removes the final answer from scoring, the two undocumented requirements that every run of the model fails, and keeps every other check.
- The proofs are about the specification in `lean/Potassium.lean` and the reference implementation. Reading records, serving searches and scoring runs are ordinary code. The model-written programs are tested and not proved.
- No clinician has reviewed the specification or the scoring. Nothing here is clinical validation or advice.

## Licence

The scripts, the Lean files and the text of the page are released under the Apache License 2.0 (`LICENSE`). Two things in this repository come from MedAgentBench and are not covered by that licence: the task's instruction and context, which the page quotes, and the potassium values in `results/worked_examples.json`. The fonts in `site/fonts/` are under the SIL Open Font License, and their licence texts are in that folder.

Directed by Will Cook. The Lean files, the scripts and the page were written with Claude. The page was then checked by further instances of Claude that had not written it. No one outside the study has reviewed it.
