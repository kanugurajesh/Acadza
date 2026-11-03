# Question Bank Doctor: evaluation report

Sample: **449 unique questions** served by Acadza's Practice DOST (6 free JEE Maths chapters × Easy/Medium/Hard, 18 assignments, collected 3 Nov 2026). Syllabus: Acadza's own JEE tree (104 chapters, 884 concepts, 2,423 sub-concepts).

## 1. Baseline: what the bank looks like today (rule-based, no AI)

| Finding | Questions | Share |
|---|---|---|
| No concept / sub-concept tag | 93 | 20.7% |
| Solution maths stored as images | 81 | 18.0% |
| Question maths stored as images | 61 | 13.6% |
| Tagged to a different chapter than the assignment requested | 35 | 7.8% |
| Sub-concept string differs from the syllabus (whitespace only) | 13 | 2.9% |
| Tagged by AI (`tagByAI`) or a teacher (`taggedByCoachingTeacher`) | 0 | 0.0% |

## 2. Making questions machine-readable

| Source of clean Markdown + LaTeX | Questions |
|---|---|
| MathML → LaTeX, deterministic converter (0 tokens) | 349 |
| Plain text, no maths markup | 39 |
| Formula images → LaTeX via vision model (one call per question) | 42 |
| Image questions not yet transcribed | 19 |

Worked solutions: 368 converted by code, 0 transcribed by vision, **81 still image-only** (their maths shows as `[[IMG:n]]` placeholders, so the answer-key check cannot read them).

MathML fragments that are malformed in Acadza's stored HTML (mismatched tags or a bare `&`; kept as a `[[MATH?]]` placeholder): **4**. Vision outputs the model marked unreadable: **2**.

Vision fidelity spot-check: **5 / 5** randomly sampled transcriptions matched the original exactly when compared by eye against the rendered question (small sample; see `eval/spotcheck_vision.json`).

## 3. Re-tagging to Acadza's syllabus

### Three tagger versions, scored the same way

Gold set: 30 questions sampled from the cases where the first tagger disagreed with Acadza on the chapter, labelled by hand **before** v2/v3 were run (labelled by the assistant, not a teacher; `eval/gold_chapter.json`). Control: 40 random questions where v1 already agreed with Acadza; a better tagger should keep them.

| Version | What the model sees | Gold correct | Control kept |
|---|---|---|---|
| Acadza (existing tags) | n/a: the current bank | 27 / 30 | 40 / 40 |
| Doctor v1 | chapter names only | 12 / 30 | 40 / 40 |
| Doctor v2 | chapter names + concept names | 1 / 2 | 1 / 3 |
| Doctor v3 | full concept → sub-concept tree of 2–3 candidate chapters | 12 / 13 | 11 / 11 |

v1 was **worse than the existing tags**. It filed binomial remainder problems under "Mathematical Reasoning" (in JEE: logic) because it only saw chapter names. That was caught by the gold set, not by eyeballing. v2 still misread "Modulus Function" as modular arithmetic. v3 reads Acadza's own sub-concept definitions (e.g. remainders are *Binomial → Application → Last digits*) and is the version used below. v2 was stopped early once v3 existed, so its row has few questions.

Final tagger (v3, `gpt-oss-120b`, strict JSON schema whose `enum` is the exact syllabus triples). Questions tagged: **38 / 449**. Every output is a valid syllabus entry by construction.

| Measure | Result |
|---|---|
| Chapter agrees with Acadza | 32 / 38 (84.2%) |
| Concept agrees (where Acadza has one) | 18 / 33 (54.5%) |
| Sub-concept agrees exactly (where Acadza has one) | 15 / 33 (45.5%) |
| Untagged questions that now have a sub-concept | 5 |

Sub-concept agreement by the tagger's own confidence (does confidence mean anything?):

| Confidence | Agreement with Acadza |
|---|---|
| ≥0.9 | 4 / 16 (25.0%) |
| 0.7–0.9 | 8 / 13 (61.5%) |
| <0.7 | 3 / 4 (75.0%) |

**Confidence does not predict agreement here; it runs the wrong way.** Two readings: the model is most confident exactly where Acadza's tag is wrong, or its self-reported confidence is uncalibrated. Until the judge and a teacher settle that, the review screen should not use confidence to skip questions.

**Off-chapter questions (6).** The Doctor files 2 under the chapter the assignment asked for (→ Acadza's chapter tag is likely wrong), 4 under Acadza's tagged chapter (→ the question really belongs elsewhere, so the *selector* served it wrongly), and 0 under a third chapter.

### Who is right when they disagree?

18 disagreements judged by `qwen/qwen3.8-27b` (Alibaba; a different model family from the OpenAI gpt-oss tagger; tags shown in random order, sources hidden).

| Verdict | Count |
|---|---|
| Doctor's tag correct, Acadza's wrong | 8 |
| Acadza's tag correct, Doctor's wrong | 9 |
| Both acceptable | 1 |
| Neither fits | 0 |

Only 18 judged so far: too few for percentages; no conclusion should be drawn yet.

By level: chapter/acadza: 2, chapter/doctor: 4, subconcept/acadza: 7, subconcept/both: 1, subconcept/doctor: 4

## 4. Answer-key verification (stratified sample)

127 questions, 20–24 per chapter. The sample was drawn per chapter with a fixed seed from the questions readable at the time, so it grew unevenly as image questions were transcribed; it is now frozen in `eval/verify_sample_ids.json`. Cascade: `gpt-oss-20b` solves blind → on disagreement `gpt-oss-120b` solves blind → if both models agree against the key, `gpt-oss-120b` reads Acadza's own worked solution.

| Outcome | Count | Share |
|---|---|---|
| Key confirmed by an independent solve | 126 | 99.2% |
| Needs a teacher (models agree against key; solution supports key or is unclear) | 1 | 0.8% |

14 of these results were computed on text later found garbled (glued LaTeX) and are waiting to be re-checked on the fixed text (rerun `run_all.py`).

The small model alone settled 122 / 127 (96.1%); only the rest needed the large model.

**Every flagged question was then solved by hand** (by the assistant; a teacher should confirm):

| Question id | Pipeline said | Hand check |
|---|---|---|
| `6a030132663ff8094ab1cd53` | key_likely_wrong | **false alarm pipeline bug**: The Doctor's MathML converter emitted a literal '<' and '>' in LaTeX; a later HTML-tag strip deleted the text between them, dropping option (C). Fixed and re-processed. |
| `6a62745a9fc11309026096c9` | needs_review | **question defect two correct options**: Single-correct question with two correct options: change option (D) or make the question multi-correct with key [B, D]. |

## 5. Near-duplicates

2 groups (4 questions) at ≥ 0.85 shingle similarity. Duplication is not a significant problem in this sample.

## 6. Cost and speed (measured from every API call)

| Stage | Model | Calls | Input tokens | Output tokens | Cost (USD) |
|---|---|---|---|---|---|
| judge | `qwen/qwen3.8-27b` | 20 | 6,066 | 834 | $0.0082 |
| normalize | `qwen/qwen3.8-27b` | 42 | 63,505 | 5,183 | $0.0715 |
| tag | `openai/gpt-oss-120b` | 89 | 145,883 | 50,862 | $0.0524 |
| verify | `openai/gpt-oss-120b` | 8 | 2,854 | 8,879 | $0.0058 |
| verify | `openai/gpt-oss-20b` | 142 | 45,290 | 163,588 | $0.0525 |
| **Total** | | 301 | 263,598 | 229,346 | **$0.1904** |

At these prices the measured spend is **$0.19** for this run. Prices: Groq public list prices (gpt-oss-120b $0.15/$0.60, gpt-oss-20b $0.075/$0.30, qwen3.8-27b $0.80/$4.00 per 1M input/output tokens).

## Method notes and limits

- Agreement with Acadza is **not** accuracy: Acadza's tags are themselves noisy (that is the point). Disagreements are adjudicated by a second model family, and a sample was checked by hand. A teacher should sign off before import.
- v3 is a *review-and-correct* tagger, not blind: Acadza's current chapter is one of its 2–3 candidate chapters (unlabelled, in sorted order). Agreement with Acadza is therefore an upper bound; the gold set and the control set are the fair measures.
- Three bugs in the Doctor itself were found and fixed during the build and are part of the record: a `<`/`>` handling bug that silently deleted text from 39 questions (it produced one false "wrong key"); a strict-JSON failure path; and LaTeX operators emitted without a trailing space (`A∩B` became the undefined `\capB`, and `\cdot p` became `\cdotp`, which silently drops the `p`), which garbled 43 questions and 150 solutions (`eval/latex_fix_ids.json`). Affected tags were redone; affected key checks are being redone (14 still pending).
- The sample covers 6 Maths chapters available on a free account. Physics/Chemistry use the same pipeline and syllabus file.
- No Acadza question text is published here beyond short excerpts; raw data stays in `data/` (git-ignored).
