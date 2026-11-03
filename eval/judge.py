"""Adjudicate tag disagreements between Acadza's existing tag and the Doctor's tag.

Judge = a different model family (Alibaba qwen3.8-27b) than the tagger (OpenAI gpt-oss-120b), to limit self-preference.
The two tags are shown as X / Y in a random order with no hint of which came from where.
Verdicts: X, Y, both (both acceptable), neither.

Usage: python -I eval/judge.py [--level chapter|subconcept|all]
Output: data/judgements.json  {_id: {level, acadza, doctor, verdict: acadza|doctor|both|neither, reason}}
"""
import argparse, json, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'doctor'))
import groq_client

JUDGE = 'qwen/qwen3.8-27b'   # Alibaba family: independent of the OpenAI gpt-oss tagger (only non-OpenAI LLM on this key)
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['verdict', 'reason'],
          'properties': {'verdict': {'type': 'string', 'enum': ['X', 'Y', 'both', 'neither']},
                         'reason': {'type': 'string'}}}
PROMPT = """You are an experienced JEE Mathematics teacher reviewing how a question is filed in a question bank.
Two candidate tags (chapter >> concept >> sub-concept) are proposed. Decide which one correctly describes what the
question primarily tests.
- "X" or "Y": that tag is correct and the other is wrong or clearly worse.
- "both": both are acceptable (e.g. the question genuinely tests both).
- "neither": neither fits.
Judge only the question content.
Reply with JSON only: {{"verdict": "X" | "Y" | "both" | "neither", "reason": "<at most 25 words>"}}

QUESTION:
{q}

Tag X: {x}
Tag Y: {y}"""


def ws(s):
    return ' '.join((s or '').split())


def fmt(t, level):
    parts = [t.get('chapter')] + ([t.get('concept'), t.get('subConcept')] if level == 'subconcept' else [])
    return ' >> '.join(p or '(none)' for p in parts)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--level', default='all'); a = ap.parse_args()
    audit = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'audit.json'), None)}
    norm = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'normalized.json'), None)}
    tags = groq_client.load_json(os.path.join(ROOT, 'data', 'tags_v3.json'), {})
    out_path = os.path.join(ROOT, 'data', 'judgements.json')
    res = groq_client.load_json(out_path, None) if os.path.exists(out_path) else {}
    todo = []
    for i, d in tags.items():
        if 'subConcept' not in d: continue
        ac = audit[i]
        if ws(ac['chapter']) != ws(d['chapter']):
            todo.append((i, 'chapter'))
        elif ac.get('subConcept') and (ws(ac['concept']) != ws(d['concept']) or ws(ac['subConcept']).lower() != ws(d['subConcept']).lower()):
            todo.append((i, 'subconcept'))
    if a.level != 'all': todo = [t for t in todo if t[1] == a.level]
    # a judgement is stale if the Doctor's tag changed since (e.g. re-tagged after a text fix) or no longer disagrees
    lvl = lambda i, level: 'subconcept' if level == 'subconcept' or audit[i].get('subConcept') else 'chapter'
    if a.level == 'all':
        live = {i for i, _ in todo}
        stale = [i for i in res if i not in live]
        for i in stale: res.pop(i)
        if stale: groq_client.save_json(out_path, res)
    todo = [(i, level) for i, level in todo if i not in res or res[i]['doctor'] != fmt(tags[i], lvl(i, level))]
    print(len(todo), 'disagreements to judge')
    for i, level in todo:
        ac, d = audit[i], tags[i]
        lv = lvl(i, level)
        acadza, doctor = fmt(ac, lv), fmt(d, lv)
        flip = random.Random(i).random() < 0.5
        x, y = (doctor, acadza) if flip else (acadza, doctor)
        try:
            out, _, _ = groq_client.chat_json(JUDGE, [{'role': 'user', 'content': PROMPT.format(q=norm[i]['question_md'][:2500], x=x, y=y)}],
                                              SCHEMA, schema_name='verdict', max_tokens=600, tag='judge', est_tokens=1500)
            if out.get('verdict') not in ('X', 'Y', 'both', 'neither'):
                raise ValueError(f'bad verdict: {out}')
        except groq_client.DailyLimit as e:
            print('daily limit:', str(e)[:150]); break
        except Exception as e:
            print('ERR', i, str(e)[:150]); continue
        v = out['verdict']
        verdict = {'both': 'both', 'neither': 'neither'}.get(v) or (('doctor' if v == 'X' else 'acadza') if flip else ('acadza' if v == 'X' else 'doctor'))
        res[i] = {'level': level, 'acadza': acadza, 'doctor': doctor, 'verdict': verdict, 'reason': out['reason'],
                  'acadza_missing_sub': not ac.get('subConcept')}
        groq_client.save_json(out_path, res)
        print(f'{verdict:8s} [{level}] {acadza[:50]}  vs  {doctor[:50]}')
    from collections import Counter
    print(Counter((v['level'], v['verdict']) for v in res.values()))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
