"""Stage 3: turn every question into clean Markdown + LaTeX.

- MathML / plain HTML questions: deterministic conversion (doctor/mathml.py), zero tokens.
- Questions whose maths is <img> fragments: one vision call on the rendered question (collect/render_questions.js).
  The deterministic text with [[IMG:n]] placeholders is sent as context, so the model only fills the gaps.

Usage: python -I doctor/normalize.py [--solutions] [--limit N] [--no-api]
Output: data/normalized.json  (list of {_id, question_md, solution_md, source, ...})
"""
import argparse, base64, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mathml import html_to_markdown
import groq_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VISION = 'qwen/qwen3.8-27b'
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['text', 'unreadable'],
          'properties': {'text': {'type': 'string'}, 'unreadable': {'type': 'boolean'}}}
PROMPT = """You are transcribing a JEE {what} that was stored as HTML with maths pasted in as small images.
The image shows the full {what} exactly as a student sees it.

Here is the machine-readable text that is already known; each [[IMG:n]] marks a place where an image of maths appears:
---
{partial}
---
Rewrite the complete {what} as Markdown with every mathematical expression in LaTeX inside $...$.
Rules:
- Transcribe exactly. Do not solve, simplify, correct or add anything.
- Keep option labels as (A) (B) (C) (D), each option on its own line.
- Replace every [[IMG:n]] with the LaTeX of what the image shows; keep all other wording.
- Set unreadable=true only if part of the image cannot be read with confidence."""


def vision(png_path, partial, what):
    with open(png_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    msgs = [{'role': 'user', 'content': [
        {'type': 'text', 'text': PROMPT.format(what=what, partial=partial or '(none)')},
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64}}]}]
    try:
        out, usage, cached = groq_client.chat_json(VISION, msgs, SCHEMA, schema_name='transcription', max_tokens=900,
                                                   tag=f'normalize-{what}', est_tokens=2600)
        return out, usage
    except groq_client.JsonFailed:
        # fall back to a plain-text answer (no constrained decoding)
        msgs[0]['content'][0]['text'] += '\n\nOutput ONLY the transcription, nothing else.'
        text, usage, _ = groq_client.chat(VISION, msgs, max_tokens=900, tag=f'normalize-{what}-plain', est_tokens=2600)
        return {'text': text.strip(), 'unreadable': False, 'fallback': True}, usage


def save(path, out, prev):
    done = {x['_id'] for x in out}
    groq_client.save_json(path, out + [p for i, p in prev.items() if i not in done])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--solutions', action='store_true', help='also transcribe image-maths solutions')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--no-api', action='store_true', help='deterministic conversion only; leave image parts pending')
    a = ap.parse_args()
    rows = groq_client.load_json(os.path.join(ROOT, 'data', 'audit.json'), None)
    out_path = os.path.join(ROOT, 'data', 'normalized.json')
    prev = {r['_id']: r for r in groq_client.load_json(out_path, None)} if os.path.exists(out_path) else {}
    out, calls, stopped = [], 0, False
    for r in rows:
        if out and len(out) % 25 == 0:   # periodic checkpoint (writing the full file after every row was O(n^2))
            save(out_path, out, prev)
        calls_before = calls
        rec = prev.get(r['_id'], {})
        q_md, q_imgs, q_fail = html_to_markdown(r['question_html'])
        s_md, s_imgs, s_fail = html_to_markdown(r['solution_html'])
        rec.update({'_id': r['_id'], 'type': r['type'], 'answer': r['answer'],
                    'question_det': q_md, 'solution_det': s_md, 'mathml_failures': q_fail + s_fail})
        for part, md, imgs, what in (('q', q_md, q_imgs, 'question'), ('s', s_md, s_imgs, 'solution')):
            key_md, key_src = f'{"question" if part == "q" else "solution"}_md', f'{part}_source'
            if not imgs:
                rec[key_md], rec[key_src] = md, 'mathml' if '$' in md else 'text'
                continue
            if rec.get(key_src) == 'vision':
                continue
            if (part == 's' and not a.solutions) or a.no_api or stopped or (a.limit and calls >= a.limit):
                # refresh the deterministic text (with [[IMG:n]] placeholders) so converter fixes reach it too
                rec[key_md], rec[key_src] = md, 'pending-vision'; continue
            png = os.path.join(ROOT, 'data', 'render', f'{r["_id"]}_{part}.png')
            try:
                v, usage = vision(png, md, what); calls += 1
            except groq_client.DailyLimit as e:
                print('daily limit reached, stopping early:', str(e)[:160]); stopped = True
                rec[key_md], rec[key_src] = md, 'pending-vision'; continue
            except Exception as e:  # never let one question stop the run
                print(f'vision FAILED {part} {r["_id"]}: {str(e)[:150]}')
                rec[key_md], rec[key_src] = md, 'vision-failed'; continue
            rec[key_md], rec[key_src], rec[f'{part}_unreadable'] = v['text'], 'vision', v['unreadable']
            print(f'vision {part} {r["_id"]}: {v["text"][:90]!r}')
        out.append(rec)
        if calls > calls_before:   # after a paid call, save at once so a crash never loses it
            save(out_path, out, prev)
    save(out_path, out, prev)
    print('question sources:', dict(Counter(x.get('q_source') for x in out)),
          '| solution sources:', dict(Counter(x.get('s_source') for x in out)), '| vision calls this run:', calls)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
