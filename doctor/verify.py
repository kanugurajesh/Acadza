"""Stage 5: answer-key verification with a cost-aware model cascade.

  S1  gpt-oss-20b solves blind (never sees Acadza's key).           agrees with key  -> 'key_confirmed'
  S2  disagreement -> gpt-oss-120b solves blind, independently.     agrees with key  -> 'key_confirmed' (S1 slip)
  S3  both models agree with each other but not the key -> 120b reads Acadza's OWN worked solution and reports the
      final answer that solution reaches.  solution == models      -> 'key_likely_wrong' (key contradicts solution)
                                           solution == key         -> 'needs_review' (models may be wrong)
  Models disagree with each other and the key                      -> 'unresolved'

Usage: python -I doctor/verify.py [--limit N] [--per-chapter N]
Output: data/verify.json
"""
import argparse, json, os, random, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groq_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SMALL, BIG = 'openai/gpt-oss-20b', 'openai/gpt-oss-120b'
LETTERS = ['A', 'B', 'C', 'D']


def schema_for(qtype):
    if qtype == 'scq':
        ans = {'type': 'string', 'enum': LETTERS}
    elif qtype == 'mcq':
        ans = {'type': 'array', 'items': {'type': 'string', 'enum': LETTERS}}
    else:
        ans = {'type': 'string'}
    return {'type': 'object', 'additionalProperties': False, 'required': ['answer', 'confidence'],
            'properties': {'answer': ans, 'confidence': {'type': 'number'}}}


RULES = {'scq': 'Exactly one option is correct. answer = its letter.',
         'mcq': 'One or more options are correct. answer = list of ALL correct letters.',
         'integerQuestion': 'The answer is a number. answer = the final numeric value only (e.g. "12" or "0.25").'}

SOLVE = """Solve this JEE Mathematics question carefully. Work it out fully before answering.
{rule}
confidence = your probability (0-1) that the answer is right.

{q}"""

READ_SOL = """Below is a JEE question and the publisher's worked solution.
Do NOT solve the question yourself. Read the worked solution and report the final answer it arrives at.
{rule}
If the solution does not reach a clear final answer, give your best reading and confidence < 0.5.

QUESTION:
{q}

WORKED SOLUTION:
{s}"""


def canon(qtype, a):
    if qtype == 'mcq':
        return tuple(sorted(set(x.strip().upper() for x in (a or []))))
    if qtype == 'scq':
        return (a or '').strip().upper()[:1]
    s = str(a or '').strip().replace(' ', '')
    try:
        return round(float(eval(s, {'__builtins__': {}}, {})) if re.fullmatch(r'[\d.+\-*/()]+', s) else float(s), 4)
    except Exception:
        return s


def same(qtype, a, b):
    x, y = canon(qtype, a), canon(qtype, b)
    if isinstance(x, float) and isinstance(y, float):
        return abs(x - y) <= max(1e-3, 1e-3 * abs(y))
    return x == y


def ask(model, prompt, qtype, effort, tag):
    out, usage, _ = groq_client.chat_json(model, [{'role': 'user', 'content': prompt}], schema_for(qtype),
                                          schema_name='answer', max_tokens=6000, reasoning_effort=effort,
                                          tag=tag, est_tokens=3500)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='max new questions this run')
    ap.add_argument('--per-chapter', type=int, default=0, help='stratified sample size per requested chapter')
    ap.add_argument('--ids', default='', help='JSON list of ids to (re)verify; existing results for them are discarded')
    a = ap.parse_args()
    norm = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'normalized.json'), None)}
    audit = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'audit.json'), None)}
    out_path = os.path.join(ROOT, 'data', 'verify.json')
    res = groq_client.load_json(out_path, None) if os.path.exists(out_path) else {}

    ready = [i for i, n in norm.items() if n.get('q_source') not in ('pending-vision', 'vision-failed')
             and n.get('question_md') and n.get('answer') not in (None, '', [])]
    if a.per_chapter:
        # Drawing the sample from "ready" questions made it drift as vision transcription finished (later runs picked
        # different questions, so some chapters ended up with >20). The sample is now drawn once and frozen on disk.
        sample_path = os.path.join(ROOT, 'eval', 'verify_sample_ids.json')
        if os.path.exists(sample_path):
            sample = groq_client.load_json(sample_path, [])
        else:
            by = defaultdict(list)
            for i in sorted(ready): by[audit[i]['requested_chapter']].append(i)
            sample = [i for ch in sorted(by) for i in random.Random(7).sample(by[ch], min(a.per_chapter, len(by[ch])))]
            groq_client.save_json(sample_path, sample)
        ok = set(ready)
        ready = [i for i in sample if i in ok]
    redo = set()
    if a.ids:   # re-check these; old results stay on file (marked stale) until replaced, so a quota stop loses nothing
        want = set(groq_client.load_json(os.path.join(ROOT, a.ids), []))
        ready = [i for i in norm if i in want]
        redo = set(ready)
        for i in ready:
            if i in res: res[i]['stale'] = True
    todo = [i for i in ready if i in redo or res.get(i, {}).get('status') is None]
    print(f'{len(ready)} in scope, {len(todo)} to do')
    done = 0
    for i in todo:
        if a.limit and done >= a.limit: break
        n = norm[i]; qt = n['type']; key = n['answer']; rule = RULES[qt]
        rec = {'type': qt, 'key': key}
        try:
            s1 = ask(SMALL, SOLVE.format(rule=rule, q=n['question_md']), qt, 'medium', 'verify-s1')
            rec['s1'] = s1
            if same(qt, s1['answer'], key):
                rec['status'] = 'key_confirmed'
            else:
                s2 = ask(BIG, SOLVE.format(rule=rule, q=n['question_md']), qt, 'medium', 'verify-s2')
                rec['s2'] = s2
                if same(qt, s2['answer'], key):
                    rec['status'] = 'key_confirmed'; rec['note'] = 'small model slipped; big model matches key'
                elif same(qt, s1['answer'], s2['answer']) and n.get('solution_md'):
                    s3 = ask(BIG, READ_SOL.format(rule=rule, q=n['question_md'], s=n['solution_md'][:5000]), qt, 'low', 'verify-s3')
                    rec['s3_solution_says'] = s3
                    if same(qt, s3['answer'], s2['answer']) and s3['confidence'] >= 0.5:
                        rec['status'] = 'key_likely_wrong'
                    elif same(qt, s3['answer'], key):
                        rec['status'] = 'needs_review'; rec['note'] = 'models agree with each other; publisher solution supports key'
                    else:
                        rec['status'] = 'needs_review'; rec['note'] = 'solution unclear'
                elif same(qt, s1['answer'], s2['answer']):
                    rec['status'] = 'needs_review'; rec['note'] = 'models agree against key; no solution text'
                else:
                    rec['status'] = 'unresolved'
        except groq_client.DailyLimit as e:
            print('daily limit reached, stopping:', str(e)[:160]); break
        except Exception as e:
            rec['status'] = None; rec['error'] = str(e)[:200]; print('ERR', i, rec['error'])
        res[i] = rec; done += 1
        groq_client.save_json(out_path, res)
        print(f"{rec.get('status')!s:18s} {i} key={key} s1={rec.get('s1', {}).get('answer')} s2={rec.get('s2', {}).get('answer', '-')}")
    st = defaultdict(int)
    for v in res.values(): st[v.get('status')] += 1
    print('status counts:', dict(st))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
