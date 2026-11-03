"""Stage 6: near-duplicate questions (different _id, same question) — deterministic, no LLM.

Text = normalized Markdown+LaTeX with whitespace/LaTeX spacing removed; similarity = Jaccard over character
5-gram shingles. Pairs above --threshold are grouped (union-find). Options are compared too, so the same
stem with different numbers is NOT flagged unless the options also match.

Usage: python -I doctor/dedupe.py [--threshold 0.85]
Output: data/duplicates.json  [{ids: [...], similarity: max_pair_sim, sample: text}]
"""
import argparse, json, os, re, sys
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def key_text(md):
    s = (md or '').lower()
    s = re.sub(r'\\(left|right|displaystyle|,|;|!|quad)', '', s)
    s = re.sub(r'[\s${}]+', '', s)
    return s


def shingles(s, k=5):
    return {s[i:i + k] for i in range(max(1, len(s) - k + 1))}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--threshold', type=float, default=0.85); a = ap.parse_args()
    norm = json.load(open(os.path.join(ROOT, 'data', 'normalized.json'), encoding='utf-8'))
    items = [(r['_id'], key_text(r.get('question_md'))) for r in norm if r.get('question_md')]
    items = [(i, t, shingles(t)) for i, t in items if len(t) >= 25]
    parent = {i: i for i, _, _ in items}

    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x

    best = {}
    for (i, ti, si), (j, tj, sj) in combinations(items, 2):
        if abs(len(ti) - len(tj)) > 0.3 * max(len(ti), len(tj)): continue
        sim = len(si & sj) / len(si | sj)
        if sim >= a.threshold:
            parent[find(i)] = find(j); best[(i, j)] = sim
    groups = {}
    for i, _, _ in items:
        groups.setdefault(find(i), []).append(i)
    text = {r['_id']: r.get('question_md', '') for r in norm}
    out = []
    for g in groups.values():
        if len(g) < 2: continue
        sims = [s for (x, y), s in best.items() if x in g and y in g]
        out.append({'ids': g, 'similarity': round(max(sims), 3), 'sample': text[g[0]][:300]})
    out.sort(key=lambda d: -d['similarity'])
    json.dump(out, open(os.path.join(ROOT, 'data', 'duplicates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(items)} questions compared; {len(out)} duplicate groups covering {sum(len(d["ids"]) for d in out)} questions')
    for d in out[:8]:
        print(f"  sim={d['similarity']} ids={d['ids']} | {d['sample'][:100]!r}")


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
