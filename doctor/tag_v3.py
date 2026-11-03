"""Tagger v3: review-and-correct with Acadza's full sub-concept definitions.

Why v3 (measured on eval/gold_chapter.json):
  v1 saw only chapter names        -> invented its own chapter meanings ("Mathematical Reasoning" for remainders)
  v2 added concept names           -> fixed P&C/Binomial, but read "Modulus Function" as modular arithmetic
  v3 shows the full concept >> sub-concept tree, but only for a few CANDIDATE chapters per question
     (the full Maths tree is ~9.3K tokens, above the free tier's 8K tokens/minute)

Candidates = {chapter the assignment asked for, Acadza's current chapter, v1's chapter}, shown in sorted order with
no indication of where each came from. The model picks one exact "chapter >> concept >> sub-concept" triple
(strict JSON enum), so the output is always a real syllabus entry.

Usage: python -I doctor/tag_v3.py [--ids eval/v2_ids.json] [--batch 6] [--out data/tags_v3.json]
"""
import argparse, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groq_client
from tag import run_robust, qblock, batches

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEP = ' >> '
PROMPT = """You are a senior JEE {subject} teacher reviewing how questions are filed in this coaching institute's
question bank. The syllabus entries below come from the institute's own syllabus: each line is
"chapter >> concept >> sub-concept". For each question choose the ONE entry that best describes the main idea
needed to solve it. Prefer the most specific matching sub-concept. The chapters offered are candidates only;
choose on the question content.
confidence: 0-1, your probability that the entry is right. reason: at most 15 words.

Syllabus entries:
{entries}

Questions:
{questions}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--subject', default='Math')
    ap.add_argument('--model', default='openai/gpt-oss-120b')
    ap.add_argument('--ids', default='')
    ap.add_argument('--batch', type=int, default=6)
    ap.add_argument('--out', default='data/tags_v3.json')
    ap.add_argument('--v1', default='data/tags_v1.json')
    ap.add_argument('--redo', action='store_true', help='with --ids: discard existing tags for those ids and re-tag')
    a = ap.parse_args()
    tax = groq_client.load_json(os.path.join(ROOT, 'data', 'taxonomy', 'jee_taxonomy.json'), None)[a.subject]
    norm = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'normalized.json'), [])}
    audit = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'audit.json'), [])}
    v1 = groq_client.load_json(os.path.join(ROOT, a.v1), {})
    out_path = os.path.join(ROOT, a.out)
    res = groq_client.load_json(out_path, {})
    ids = [i for i, n in norm.items() if n.get('q_source') != 'pending-vision' and n.get('question_md')]
    if a.ids:
        want = set(groq_client.load_json(os.path.join(ROOT, a.ids), []))
        ids = [i for i in ids if i in want]
        if a.redo:
            for i in ids: res.pop(i, None)
    todo = [i for i in ids if i not in res]
    chapters = {c.lower(): c for c in tax}

    def candidates(i):
        req = audit[i]['requested_chapter'].lower()
        req = next((c for k, c in chapters.items() if k.replace('(', '').replace(')', '').startswith(req[:14])), None)
        cs = {req, audit[i]['chapter'], v1.get(i, {}).get('chapter')}
        return tuple(sorted(c for c in cs if c in tax))

    groups = defaultdict(list)
    for i in todo: groups[candidates(i)].append(i)
    print(f'{len(todo)} to tag in {len(groups)} candidate groups -> {a.out}')
    for cands, gids in groups.items():
        entries = [f'{ch}{SEP}{co}{SEP}{sub}' for ch in cands for co, subs in tax[ch].items() for sub in subs]
        for b in batches(gids, a.batch):
            pairs = [(f'q{k + 1}', norm[i]) for k, i in enumerate(b)]
            mk = lambda ps, e=entries: PROMPT.format(subject=a.subject, entries='\n'.join(f'- {x}' for x in e), questions=qblock(ps))
            try:
                got = run_robust(a.model, mk, pairs, entries, 'entry', 'tag-v3')
            except groq_client.DailyLimit as e:
                print('daily limit:', str(e)[:160]); groq_client.save_json(out_path, res); return
            for (qid, _), i in zip(pairs, b):
                if qid in got:
                    ch, co, sub = got[qid]['entry'].split(SEP, 2)
                    res[i] = {'chapter': ch, 'concept': co, 'subConcept': sub, 'chapter_conf': got[qid].get('confidence'),
                              'sub_conf': got[qid].get('confidence'), 'chapter_reason': got[qid].get('reason', ''),
                              'sub_reason': got[qid].get('reason', ''), 'candidates': list(cands),
                              'sub_snapped': bool(got[qid].get('snapped'))}
            groq_client.save_json(out_path, res)
            print(f'v3 {" | ".join(c[:14] for c in cands)}  +{len(b)}')
    print('tagged:', len(res))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
