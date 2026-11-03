"""Score tagger versions against the gold chapter set and the control set.

gold    : eval/gold_chapter.json - 30 sampled v1-vs-Acadza chapter disagreements, labelled before v2/v3 ran
control : eval/v2_control_ids.json - 40 random questions where v1 already agreed with Acadza; a good revision
          should keep (almost) all of them

Usage: python -I eval/compare_taggers.py
Writes data/tagger_comparison.json
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'doctor'))
import groq_client as g


def main():
    gold = json.load(open(os.path.join(ROOT, 'eval', 'gold_chapter.json'), encoding='utf-8'))['labels']
    ctrl = g.load_json(os.path.join(ROOT, 'eval', 'v2_control_ids.json'), [])
    A = {r['_id']: r for r in g.load_json(os.path.join(ROOT, 'data', 'audit.json'), [])}
    versions = {'Acadza (existing tags)': {i: {'chapter': A[i]['chapter']} for i in A}}
    for v in ('v1', 'v2', 'v3'):
        versions[f'Doctor {v}'] = g.load_json(os.path.join(ROOT, 'data', f'tags_{v}.json'), {})
    out = {}
    print(f'{"version":24s} {"gold correct":>16s} {"control kept":>16s}')
    for name, T in versions.items():
        gs = [i for i in gold if i in T and T[i].get('chapter')]
        gc = sum(T[i]['chapter'] in gold[i]['ok'] for i in gs)
        cs = [i for i in ctrl if i in T and T[i].get('chapter')]
        ck = sum(T[i]['chapter'] == A[i]['chapter'] for i in cs)
        out[name] = {'gold_correct': gc, 'gold_n': len(gs), 'control_kept': ck, 'control_n': len(cs)}
        print(f'{name:24s} {gc:>7d} / {len(gs):<6d} {ck:>7d} / {len(cs):<6d}')
    g.save_json(os.path.join(ROOT, 'data', 'tagger_comparison.json'), out)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
