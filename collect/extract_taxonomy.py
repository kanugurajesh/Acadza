"""Extract Acadza's syllabus trees from the public Next.js JS chunks.

Finds JS object literals shaped {chapter: {concept: [subconcept, ...]}} (optionally wrapped in
{Subject: {...}}), converts them to JSON (bare keys, single-quoted strings) and dumps them.

Usage: python -I extract_taxonomy.py <out.json> <chunk.js> [<chunk.js> ...]
"""
import json, re, sys

BS, SQ, DQ = chr(92), chr(39), chr(34)
KEY = r'(?:"[^"]{1,160}"|\'[^\']{1,160}\'|[A-Za-z_$][\w$]*)'
START = re.compile(r'\{' + KEY + r':\{' + KEY + r':(?:\{' + KEY + r':)?\[[' + DQ + SQ + r']')
IDENT = re.compile(r'[A-Za-z_$][\w$]*')


def brace_match(src, i):
    """Index just past the '}' matching the '{' at i, honouring '...' and "..." strings."""
    depth, quote, esc = 0, None, False
    for j in range(i, len(src)):
        c = src[j]
        if quote:
            if esc: esc = False
            elif c == BS: esc = True
            elif c == quote: quote = None
        elif c in (SQ, DQ): quote = c
        elif c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return j + 1
    return None


def js_to_json(lit):
    """Tokenise a JS object literal made of strings/arrays/objects into JSON text."""
    out, i, n = [], 0, len(lit)
    while i < n:
        c = lit[i]
        if c in (SQ, DQ):
            j, buf = i + 1, []
            while lit[j] != c:
                if lit[j] == BS:
                    e = lit[j + 1]
                    if e == 'x': buf.append(chr(int(lit[j + 2:j + 4], 16))); j += 4
                    elif e == 'u' and lit[j + 2] == '{':
                        k = lit.index('}', j); buf.append(chr(int(lit[j + 3:k], 16))); j = k + 1
                    elif e == 'u': buf.append(chr(int(lit[j + 2:j + 6], 16))); j += 6
                    else: buf.append({'n': '\n', 't': '\t', 'r': '\r'}.get(e, e)); j += 2
                else: buf.append(lit[j]); j += 1
            out.append(json.dumps(''.join(buf), ensure_ascii=False)); i = j + 1
        elif c.isalpha() or c in '_$':
            m = IDENT.match(lit, i); word = m.group(0); i = m.end()
            out.append(word if word in ('true', 'false', 'null') else json.dumps(word))
        else:
            out.append(c); i += 1
    return ''.join(out)


def is_tree(o):
    return isinstance(o, dict) and len(o) >= 3 and all(
        isinstance(v, dict) and v and all(isinstance(x, list) and all(isinstance(y, str) for y in x) for x in v.values())
        for v in o.values())


def flatten(o):
    if is_tree(o): return [{'subject': None, 'tree': o}]
    if isinstance(o, dict) and o and all(is_tree(v) for v in o.values()):
        return [{'subject': k, 'tree': v} for k, v in o.items()]
    return []


def extract(src):
    found, covered_until = [], -1
    for m in START.finditer(src):
        if m.start() < covered_until: continue
        end = brace_match(src, m.start())
        if not end: continue
        try: obj = json.loads(js_to_json(src[m.start():end]))
        except Exception: continue
        trees = flatten(obj)
        if trees:
            found.extend(trees); covered_until = end
    return found


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    out, files = sys.argv[1], sys.argv[2:]
    allt = []
    for f in files:
        for t in extract(open(f, encoding='utf-8').read()):
            t['source'] = f.replace(BS, '/').split('/')[-1]
            allt.append(t)
    for k, t in enumerate(allt):
        o = t['tree']; nc = sum(len(v) for v in o.values()); ns = sum(len(x) for v in o.values() for x in v.values())
        print(f"[{k}] {t['source'][:28]} subject={t['subject']} chapters={len(o)} concepts={nc} subconcepts={ns} first={list(o)[:2]}")
    json.dump(allt, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
