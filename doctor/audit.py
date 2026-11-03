"""Rule-based baseline audit of collected Acadza questions (no LLM).

Usage: python -I doctor/audit.py [raw_dir] [taxonomy.json] [out.json]
Writes a per-question record list (unique by _id) with structural flags, and prints a summary.
"""
import glob, html, json, os, re, sys
from collections import Counter

RAW = sys.argv[1] if len(sys.argv) > 1 else 'data/raw'
TAX = sys.argv[2] if len(sys.argv) > 2 else 'data/taxonomy/jee_taxonomy.json'
OUT = sys.argv[3] if len(sys.argv) > 3 else 'data/audit.json'
TYPES = ('scq', 'mcq', 'integerQuestion', 'passageQuestion', 'matchQuestion')
IMG = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def text_of(h):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', h or '')).split())


def body_of(q):
    for t in TYPES:
        b = q.get(t)
        if isinstance(b, dict) and (b.get('question') or b.get('quesImages') or b.get('answer') not in (None, '', [])):
            return t, b
    return None, {}


def main():
    tax = json.load(open(TAX, encoding='utf-8'))
    math = tax['Math']
    seen, rows, dup_hits = {}, [], 0
    for f in sorted(glob.glob(os.path.join(RAW, '*.json'))):
        stem = os.path.basename(f)[:-5]
        requested_ch, requested_lv = stem.rsplit('__', 1)
        requested_ch, requested_lv = requested_ch.strip('_'), requested_lv.strip('_')
        for q in json.load(open(f, encoding='utf-8'))['questions']:
            if q['_id'] in seen:
                dup_hits += 1; seen[q['_id']]['seen_in'].append(os.path.basename(f)); continue
            t, b = body_of(q)
            qh, sh = b.get('question', '') or '', b.get('solution', '') or ''
            ch, co, sub = q.get('chapter'), q.get('concept'), q.get('subConcept')
            requested = requested_ch.replace('_', ' ').strip()
            flags = []
            if ch and not ch.replace('(', '').replace(')', '').replace(' ', '').lower().startswith(requested.replace(' ', '').lower()[:12]):
                flags.append('off_portion')
            if not co: flags.append('missing_concept')
            if not sub: flags.append('missing_subconcept')
            if ch and ch not in math: flags.append('chapter_not_in_taxonomy')
            elif co and co not in math.get(ch, {}): flags.append('concept_not_in_taxonomy')
            elif sub and sub not in math.get(ch, {}).get(co, []): flags.append('subconcept_not_in_taxonomy')
            qimgs, simgs = IMG.findall(qh), IMG.findall(sh)
            if qimgs: flags.append('math_as_image_in_question')
            if simgs: flags.append('math_as_image_in_solution')
            if len(text_of(qh)) < 15 and not qimgs: flags.append('empty_question_text')
            if not text_of(sh) and not simgs: flags.append('no_solution')
            if b.get('answer') in (None, '', []): flags.append('no_answer_key')
            if (q.get('level') or '').upper() != requested_lv.upper(): flags.append('level_mismatch')
            rec = {
                '_id': q['_id'], 'type': t, 'requested_chapter': requested, 'requested_level': requested_lv,
                'chapter': ch, 'concept': co, 'subConcept': sub, 'level': q.get('level'), 'difficulty': q.get('difficulty'),
                'previousExam': q.get('previousExam'), 'previousExamYear': q.get('previousExamYear'),
                'tagByAI': q.get('tagByAI'), 'taggedByCoachingTeacher': q.get('taggedByCoachingTeacher'),
                'q_images': qimgs, 's_images': simgs, 'question_html': qh, 'solution_html': sh,
                'answer': b.get('answer'), 'question_text': text_of(qh), 'flags': flags,
                'seen_in': [os.path.basename(f)],
            }
            seen[q['_id']] = rec; rows.append(rec)
    json.dump(rows, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    n = len(rows); fc = Counter(fl for r in rows for fl in r['flags'])
    print(f'unique questions: {n}  (duplicate hits across assignments: {dup_hits})')
    print('types:', dict(Counter(r['type'] for r in rows)))
    print('tagByAI true:', sum(1 for r in rows if r['tagByAI']), '| teacher-tagged:', sum(1 for r in rows if r['taggedByCoachingTeacher']))
    print('PYQ-tagged:', sum(1 for r in rows if r['previousExam']))
    for k, v in fc.most_common():
        print(f'  {k:32s} {v:4d}  ({v / n:5.1%})')
    print('any flag (excluding level_mismatch):', sum(1 for r in rows if set(r['flags']) - {'level_mismatch'}), '/', n)
    print('off-portion chapters:', dict(Counter(r['chapter'] for r in rows if 'off_portion' in r['flags'])))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
