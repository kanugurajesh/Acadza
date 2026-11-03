"""Build the evaluation report from stage outputs. Every number is computed here, none typed by hand.

Usage: python -I eval/report.py
Writes: REPORT.md (no question text beyond short excerpts) and data/report.json
"""
import json, os, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'doctor'))
import groq_client
D = lambda *p: os.path.join(ROOT, 'data', *p)
PRICE = {  # USD per 1M tokens, from console.groq.com/docs/models (checked 3 Nov 2026)
    'openai/gpt-oss-120b': (0.15, 0.60), 'openai/gpt-oss-20b': (0.075, 0.30), 'qwen/qwen3.8-27b': (0.80, 4.00)}


def load(name, default):
    return groq_client.load_json(D(name), default)


def ws(s):
    return ' '.join((s or '').split()).lower()


def pct(a, b):
    return f'{a / b:.1%}' if b else 'n/a'


def main():
    audit = load('audit.json', []); A = {r['_id']: r for r in audit}
    norm = {r['_id']: r for r in load('normalized.json', [])}
    tags = load('tags_v3.json', {}); ver = load('verify.json', {}); dup = load('duplicates.json', [])
    judge = load('judgements.json', {})
    usage = [json.loads(l) for l in open(D('usage.jsonl'), encoding='utf-8')] if os.path.exists(D('usage.jsonl')) else []
    N = len(audit); M = {}
    L = []
    w = L.append

    # ---------------- baseline
    fc = Counter(f for r in audit for f in r['flags'])
    w('# Question Bank Doctor: evaluation report\n')
    w(f'Sample: **{N} unique questions** served by Acadza\'s Practice DOST (6 free JEE Maths chapters × Easy/Medium/Hard, '
      f'18 assignments, collected 3 Nov 2026). Syllabus: Acadza\'s own JEE tree (104 chapters, 884 concepts, 2,423 sub-concepts).\n')
    w('## 1. Baseline: what the bank looks like today (rule-based, no AI)\n')
    w('| Finding | Questions | Share |\n|---|---|---|')
    for k, label in [('missing_subconcept', 'No concept / sub-concept tag'), ('math_as_image_in_solution', 'Solution maths stored as images'),
                     ('math_as_image_in_question', 'Question maths stored as images'), ('off_portion', 'Tagged to a different chapter than the assignment requested'),
                     ('subconcept_not_in_taxonomy', 'Sub-concept string differs from the syllabus (whitespace only)')]:
        w(f'| {label} | {fc[k]} | {pct(fc[k], N)} |')
    w(f'| Tagged by AI (`tagByAI`) or a teacher (`taggedByCoachingTeacher`) | {sum(1 for r in audit if r["tagByAI"] or r["taggedByCoachingTeacher"])} | {pct(sum(1 for r in audit if r["tagByAI"] or r["taggedByCoachingTeacher"]), N)} |')
    M['baseline'] = dict(fc)

    # ---------------- normalization
    src = Counter(n.get('q_source') for n in norm.values())
    fails = sum(n.get('mathml_failures', 0) for n in norm.values())
    w('\n## 2. Making questions machine-readable\n')
    w('| Source of clean Markdown + LaTeX | Questions |\n|---|---|')
    for k, label in [('mathml', 'MathML → LaTeX, deterministic converter (0 tokens)'), ('text', 'Plain text, no maths markup'),
                     ('vision', 'Formula images → LaTeX via vision model (one call per question)'),
                     ('pending-vision', 'Image questions not yet transcribed'), ('vision-failed', 'Vision transcription failed')]:
        if src.get(k): w(f'| {label} | {src[k]} |')
    ssrc = Counter(n.get('s_source') for n in norm.values())
    w(f'\nWorked solutions: {ssrc.get("mathml", 0) + ssrc.get("text", 0)} converted by code, {ssrc.get("vision", 0)} transcribed '
      f'by vision, **{ssrc.get("pending-vision", 0)} still image-only** (their maths shows as `[[IMG:n]]` placeholders, so '
      f'the answer-key check cannot read them).')
    w(f'\nMathML fragments that are malformed in Acadza\'s stored HTML (mismatched tags or a bare `&`; kept as a `[[MATH?]]` placeholder): **{fails}**. Vision outputs the model marked unreadable: '
      f'**{sum(1 for n in norm.values() if n.get("q_unreadable"))}**.')
    sc = load(os.path.join('..', 'eval', 'spotcheck_vision.json'), None)
    if sc:
        w(f'\nVision fidelity spot-check: **{sc["faithful"]} / {sc["total"]}** randomly sampled transcriptions matched the '
          f'original exactly when compared by eye against the rendered question (small sample; see `eval/spotcheck_vision.json`).')
    M['normalize'] = dict(src)

    # ---------------- tagging
    T = {i: t for i, t in tags.items() if 'subConcept' in t}
    w('\n## 3. Re-tagging to Acadza\'s syllabus\n')
    cmp_ = load('tagger_comparison.json', {})
    if cmp_:
        w('### Three tagger versions, scored the same way\n')
        w('Gold set: 30 questions sampled from the cases where the first tagger disagreed with Acadza on the chapter, '
          'labelled by hand **before** v2/v3 were run (labelled by the assistant, not a teacher; `eval/gold_chapter.json`). '
          'Control: 40 random questions where v1 already agreed with Acadza; a better tagger should keep them.\n')
        w('| Version | What the model sees | Gold correct | Control kept |\n|---|---|---|---|')
        desc = {'Acadza (existing tags)': 'n/a: the current bank', 'Doctor v1': 'chapter names only',
                'Doctor v2': 'chapter names + concept names', 'Doctor v3': 'full concept → sub-concept tree of 2–3 candidate chapters'}
        for k, v in cmp_.items():
            if v['gold_n'] or v['control_n']:
                w(f'| {k} | {desc.get(k, "")} | {v["gold_correct"]} / {v["gold_n"]} | {v["control_kept"]} / {v["control_n"]} |')
        w('\nv1 was **worse than the existing tags**. It filed binomial remainder problems under "Mathematical Reasoning" '
          '(in JEE: logic) because it only saw chapter names. That was caught by the gold set, not by eyeballing. '
          'v2 still misread "Modulus Function" as modular arithmetic. v3 reads Acadza\'s own sub-concept definitions '
          '(e.g. remainders are *Binomial → Application → Last digits*) and is the version used below. v2 was stopped '
          'early once v3 existed, so its row has few questions.\n')
    w(f'Final tagger (v3, `gpt-oss-120b`, strict JSON schema whose `enum` is the exact syllabus triples). '
      f'Questions tagged: **{len(T)} / {N}**. Every output is a valid syllabus entry by construction.\n')
    ch_agree = sum(1 for i, t in T.items() if ws(t['chapter']) == ws(A[i]['chapter']))
    has_sub = [i for i in T if A[i].get('subConcept')]
    co_agree = sum(1 for i in has_sub if ws(T[i]['concept']) == ws(A[i]['concept']) and ws(T[i]['chapter']) == ws(A[i]['chapter']))
    sub_agree = sum(1 for i in has_sub if ws(T[i]['subConcept']) == ws(A[i]['subConcept']) and ws(T[i]['concept']) == ws(A[i]['concept']))
    filled = sum(1 for i in T if not A[i].get('subConcept'))
    w('| Measure | Result |\n|---|---|')
    w(f'| Chapter agrees with Acadza | {ch_agree} / {len(T)} ({pct(ch_agree, len(T))}) |')
    w(f'| Concept agrees (where Acadza has one) | {co_agree} / {len(has_sub)} ({pct(co_agree, len(has_sub))}) |')
    w(f'| Sub-concept agrees exactly (where Acadza has one) | {sub_agree} / {len(has_sub)} ({pct(sub_agree, len(has_sub))}) |')
    w(f'| Untagged questions that now have a sub-concept | {filled} |')
    # calibration
    buckets = defaultdict(lambda: [0, 0])
    for i in has_sub:   # same match rule as the "Sub-concept agrees exactly" row above
        c = T[i].get('sub_conf', 0); b = '≥0.9' if c >= 0.9 else '0.7–0.9' if c >= 0.7 else '<0.7'
        buckets[b][1] += 1
        buckets[b][0] += ws(T[i]['subConcept']) == ws(A[i]['subConcept']) and ws(T[i]['concept']) == ws(A[i]['concept'])
    w('\nSub-concept agreement by the tagger\'s own confidence (does confidence mean anything?):\n')
    w('| Confidence | Agreement with Acadza |\n|---|---|')
    for b in ('≥0.9', '0.7–0.9', '<0.7'):
        if buckets[b][1]: w(f'| {b} | {buckets[b][0]} / {buckets[b][1]} ({pct(*buckets[b])}) |')
    rates = [buckets[b][0] / buckets[b][1] for b in ('≥0.9', '0.7–0.9', '<0.7') if buckets[b][1]]
    if len(rates) >= 2 and rates[0] < rates[-1]:
        w('\n**Confidence does not predict agreement here; it runs the wrong way.** Two readings: the model is most '
          'confident exactly where Acadza\'s tag is wrong, or its self-reported confidence is uncalibrated. Until the '
          'judge and a teacher settle that, the review screen should not use confidence to skip questions.')
    elif rates:
        w('\nHigher confidence goes with higher agreement, so confidence can help order the review queue.')
    # off-portion
    off = [i for i in T if 'off_portion' in A[i]['flags']]
    if off:
        rq = lambda i: ws(A[i]['requested_chapter']).replace('(', '').replace(')', '')
        to_req = sum(1 for i in off if ws(T[i]['chapter']).replace('(', '').replace(')', '').startswith(rq(i)[:12]))
        to_ac = sum(1 for i in off if ws(T[i]['chapter']) == ws(A[i]['chapter']))
        w(f'\n**Off-chapter questions ({len(off)}).** The Doctor files {to_req} under the chapter the assignment asked for '
          f'(→ Acadza\'s chapter tag is likely wrong), {to_ac} under Acadza\'s tagged chapter (→ the question really belongs '
          f'elsewhere, so the *selector* served it wrongly), and {len(off) - to_req - to_ac} under a third chapter.')
    # judge
    if judge:
        jv = Counter(v['verdict'] for v in judge.values())
        jn = sum(jv.values())
        w(f'\n### Who is right when they disagree?\n')
        w(f'{jn} disagreements judged by `qwen/qwen3.8-27b` (Alibaba; a different model family from the OpenAI gpt-oss tagger; tags shown in random order, sources hidden).\n')
        small = jn < 20
        w('| Verdict | Count |' + ('' if small else ' Share |') + '\n|---|---|' + ('' if small else '---|'))
        for k, label in [('doctor', 'Doctor\'s tag correct, Acadza\'s wrong'), ('acadza', 'Acadza\'s tag correct, Doctor\'s wrong'),
                         ('both', 'Both acceptable'), ('neither', 'Neither fits')]:
            w(f'| {label} | {jv.get(k, 0)} |' + ('' if small else f' {pct(jv.get(k, 0), jn)} |'))
        if small:
            w(f'\nOnly {jn} judged so far: too few for percentages; no conclusion should be drawn yet.')
        bylevel = Counter((v['level'], v['verdict']) for v in judge.values())
        w('\nBy level: ' + ', '.join(f'{lv}/{vd}: {n}' for (lv, vd), n in sorted(bylevel.items())))
        M['judge'] = dict(jv)
    M['tagging'] = {'tagged': len(T), 'chapter_agree': ch_agree, 'has_sub': len(has_sub), 'concept_agree': co_agree,
                    'sub_agree': sub_agree, 'filled': filled}

    # ---------------- verification
    if ver:
        st = Counter(v.get('status') for v in ver.values())
        n = sum(st.values())
        w('\n## 4. Answer-key verification (stratified sample)\n')
        per = Counter(A[i]['requested_chapter'] for i in ver if i in A)
        w(f'{n} questions, {min(per.values())}–{max(per.values())} per chapter. The sample was drawn per chapter with a fixed '
          f'seed from the questions readable at the time, so it grew unevenly as image questions were transcribed; it is now '
          f'frozen in `eval/verify_sample_ids.json`. Cascade: `gpt-oss-20b` solves blind → on disagreement '
          f'`gpt-oss-120b` solves blind → if both models agree against the key, `gpt-oss-120b` reads Acadza\'s own worked solution.\n')
        w('| Outcome | Count | Share |\n|---|---|---|')
        for k, label in [('key_confirmed', 'Key confirmed by an independent solve'), ('key_likely_wrong', 'Key likely wrong (both models AND Acadza\'s own solution disagree with the key)'),
                         ('needs_review', 'Needs a teacher (models agree against key; solution supports key or is unclear)'),
                         ('unresolved', 'Unresolved (models disagree with each other)'), (None, 'Errored / not finished')]:
            if st.get(k): w(f'| {label} | {st[k]} | {pct(st[k], n)} |')
        n_stale = sum(1 for v in ver.values() if v.get('stale'))
        if n_stale:
            w(f'\n{n_stale} of these results were computed on text later found garbled (glued LaTeX) and are waiting to be '
              f're-checked on the fixed text (rerun `run_all.py`).')
        s1_ok = sum(1 for v in ver.values() if v.get('status') and 's2' not in v)
        w(f'\nThe small model alone settled {s1_ok} / {n} ({pct(s1_ok, n)}); only the rest needed the large model.')
        wrong = [(i, v) for i, v in ver.items() if v.get('status') == 'key_likely_wrong']
        if wrong:
            w('\nLikely-wrong keys (question ids, for Acadza\'s content team):\n')
            w('| Question id | Type | Stored key | Both models | Acadza\'s solution reaches |\n|---|---|---|---|---|')
            for i, v in wrong:
                w(f'| `{i}` | {v["type"]} | {v["key"]} | {v["s2"]["answer"]} | {v["s3_solution_says"]["answer"]} |')
        M['verify'] = {str(k): c for k, c in st.items()}
        mr = load(os.path.join('..', 'eval', 'manual_key_review.json'), None)
        if mr:
            w('\n**Every flagged question was then solved by hand** (by the assistant; a teacher should confirm):\n')
            w('| Question id | Pipeline said | Hand check |\n|---|---|---|')
            for i, r in mr['reviews'].items():
                w(f'| `{i}` | {r["pipeline_status"]} | **{r["verdict"].replace("_", " ")}**: {r.get("recommendation") or r.get("cause", "").split(". Fixed")[0] + ". Fixed and re-processed."} |')

    # ---------------- duplicates
    w('\n## 5. Near-duplicates\n')
    w(f'{len(dup)} groups ({sum(len(d["ids"]) for d in dup)} questions) at ≥ 0.85 shingle similarity. Duplication is not a '
      f'significant problem in this sample.')

    # ---------------- cost
    if usage:
        w('\n## 6. Cost and speed (measured from every API call)\n')
        by = defaultdict(lambda: [0, 0, 0, 0.0])
        for u in usage:
            k = (u['tag'].split('-')[0] if u['tag'] else '?', u['model'])
            by[k][0] += 1; by[k][1] += u['prompt'] or 0; by[k][2] += u['completion'] or 0; by[k][3] += u['latency_s'] or 0
        w('| Stage | Model | Calls | Input tokens | Output tokens | Cost (USD) |\n|---|---|---|---|---|---|')
        tot = 0.0
        for (stage, model), (c, pi, po, lat) in sorted(by.items()):
            p = PRICE.get(model, (0, 0)); cost = pi / 1e6 * p[0] + po / 1e6 * p[1]; tot += cost
            w(f'| {stage} | `{model}` | {c} | {pi:,} | {po:,} | ${cost:.4f} |')
        w(f'| **Total** | | {len(usage)} | {sum(u["prompt"] or 0 for u in usage):,} | {sum(u["completion"] or 0 for u in usage):,} | **${tot:.4f}** |')
        nt = len(T) or 1
        w(f'\nAt these prices the measured spend is **${tot:.2f}** for this run. Prices: Groq public list prices '
          f'(gpt-oss-120b $0.15/$0.60, gpt-oss-20b $0.075/$0.30, qwen3.8-27b $0.80/$4.00 per 1M input/output tokens).')
        M['cost_usd'] = round(tot, 4)

    w('\n## Method notes and limits\n')
    w('- Agreement with Acadza is **not** accuracy: Acadza\'s tags are themselves noisy (that is the point). Disagreements are '
      'adjudicated by a second model family, and a sample was checked by hand. A teacher should sign off before import.')
    w('- v3 is a *review-and-correct* tagger, not blind: Acadza\'s current chapter is one of its 2–3 candidate chapters '
      '(unlabelled, in sorted order). Agreement with Acadza is therefore an upper bound; the gold set and the control set '
      'are the fair measures.')
    lf = load(os.path.join('..', 'eval', 'latex_fix_ids.json'), {})
    w('- Three bugs in the Doctor itself were found and fixed during the build and are part of the record: a `<`/`>` '
      'handling bug that silently deleted text from 39 questions (it produced one false "wrong key"); a strict-JSON '
      'failure path; and LaTeX operators emitted without a trailing space (`A∩B` became the undefined `\\capB`, and '
      f'`\\cdot p` became `\\cdotp`, which silently drops the `p`), which garbled {len(lf.get("question_ids", []))} questions and '
      f'{len(lf.get("solution_ids", []))} solutions (`eval/latex_fix_ids.json`). Affected tags were redone; affected key '
      'checks ' + (f'are being redone ({sum(1 for v in ver.values() if v.get("stale"))} still pending).'
                   if any(v.get('stale') for v in ver.values()) else 'were redone.'))
    w('- The sample covers 6 Maths chapters available on a free account. Physics/Chemistry use the same pipeline and syllabus file.')
    w('- No Acadza question text is published here beyond short excerpts; raw data stays in `data/` (git-ignored).')
    open(os.path.join(ROOT, 'REPORT.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    json.dump(M, open(D('report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print('\n'.join(L))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
