"""Stage 4: blind re-tagging to Acadza's own syllabus.

Two passes, both with strict JSON schemas whose `enum`s are Acadza's exact syllabus strings, so the model
cannot invent or misspell a tag:
  T1  chapter         : batches of questions, enum = all chapter names of the subject
  T2  concept/subconcept: questions grouped by T1 chapter, enum = "concept >> subconcept" pairs of that chapter
The model never sees Acadza's existing tag (blind), so agreement with it is a fair measurement.

Usage: python -I doctor/tag.py [--subject Math] [--t1-model ...] [--t2-model ...] [--batch 8]
Output: data/tags.json  {_id: {chapter, concept, subConcept, chapter_conf, sub_conf, chapter_reason, sub_reason}}
"""
import argparse, difflib, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groq_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEP = ' >> '


def norm_ws(s):
    return ' '.join((s or '').split())


def batches(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def item_schema(ids, field_enum, field):
    return {'type': 'object', 'additionalProperties': False, 'required': ['items'], 'properties': {'items': {
        'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                   'required': ['qid', field, 'confidence', 'reason'],
                                   'properties': {'qid': {'type': 'string', 'enum': ids},
                                                  field: {'type': 'string', 'enum': field_enum},
                                                  'confidence': {'type': 'number'},
                                                  'reason': {'type': 'string'}}}}}}


def qblock(batch):
    return '\n\n'.join(f'[{qid}]\n{q["question_md"][:1800]}' for qid, q in batch)


T1 = """You are a senior JEE {subject} teacher tagging questions in a question bank.
For each question, choose the ONE chapter from the list whose concept the question primarily tests.
If a question mixes chapters, pick the chapter a teacher would file it under (the main idea needed to solve it).
confidence: 0-1, your probability that the chapter is right. reason: at most 15 words.

Chapters:
{chapters}"""

# v2: v1 saw only chapter names and used its own idea of each chapter (e.g. filed binomial remainder problems under
# "Mathematical Reasoning", which in JEE means logic). v2 shows each chapter's concept list as its definition.
T1_V2 = """You are a senior JEE {subject} teacher tagging questions in this coaching institute's question bank.
For each question, choose the ONE chapter it belongs to IN THIS INSTITUTE'S SYLLABUS.
Each chapter is defined by the concepts listed after it: file a question under the chapter whose listed concepts
contain the main idea needed to solve it (e.g. remainder problems solved by binomial expansion belong to the chapter
listing binomial applications; sums of binomial coefficients belong to the chapter listing binomial coefficients).
Use the chapter whose concept list best covers the question even if another chapter name sounds related.
confidence: 0-1, your probability that the chapter is right. reason: at most 15 words, name the matching concept.

Chapters (chapter: its concepts):
{chapters}

Questions:
{questions}"""

T2 = """You are a senior JEE {subject} teacher tagging questions in the chapter "{chapter}".
For each question choose the ONE "concept >> sub-concept" pair from the list that the question primarily tests.
confidence: 0-1, your probability that the pair is right. reason: at most 15 words.

Pairs:
{pairs}

Questions:
{questions}"""


def run_pass(model, prompt, schema, tag, max_tokens=4000, effort='low'):
    out, usage, cached = groq_client.chat_json(model, [{'role': 'user', 'content': prompt}], schema,
                                               schema_name='tags', max_tokens=max_tokens, reasoning_effort=effort,
                                               tag=tag, est_tokens=len(prompt) // 3 + max_tokens // 2)
    return {it['qid']: it for it in out['items']}


def run_robust(model, make_prompt, pairs, enum, field, tag):
    """Batch call; if Groq's constrained decoding still emits an out-of-enum value, retry one question at a time,
    and as a last resort take a JSON-mode answer and snap it to the nearest valid syllabus string (marked 'snapped')."""
    ids = [p for p, _ in pairs]
    try:
        return run_pass(model, make_prompt(pairs), item_schema(ids, enum, field), tag)
    except groq_client.JsonFailed:
        pass
    got = {}
    for qid, q in pairs:
        one = [(qid, q)]
        try:
            got.update(run_pass(model, make_prompt(one), item_schema([qid], enum, field), tag + '-single'))
            continue
        except groq_client.JsonFailed:
            pass
        prompt = make_prompt(one) + (f'\n\nReply with JSON only: {{"items": [{{"qid": "{qid}", "{field}": "<copy one entry '
                                     f'from the list exactly>", "confidence": <0-1>, "reason": "<short>"}}]}}')
        content, _, _ = groq_client.chat(model, [{'role': 'user', 'content': prompt}], json_mode=True, max_tokens=3000,
                                         reasoning_effort='low', tag=tag + '-snap', est_tokens=len(prompt) // 3 + 1500)
        try:
            it = json.loads(content)['items'][0]
        except Exception:
            continue
        near = difflib.get_close_matches(str(it.get(field, '')), enum, n=1, cutoff=0.0)
        if near:
            it[field], it['snapped'] = near[0], True
            got[qid] = it
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--subject', default='Math')
    ap.add_argument('--t1-model', default='openai/gpt-oss-120b')
    ap.add_argument('--t2-model', default='openai/gpt-oss-120b')
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--max-batches', type=int, default=0, help='stop after N LLM calls per pass (testing)')
    ap.add_argument('--version', default='v2', choices=['v1', 'v2'], help='v1: chapter names only; v2: names + concept lists')
    ap.add_argument('--out', default='data/tags.json')
    ap.add_argument('--ids', default='', help='JSON file with a list of question ids to tag (default: all ready)')
    a = ap.parse_args()
    tax = groq_client.load_json(os.path.join(ROOT, 'data', 'taxonomy', 'jee_taxonomy.json'), None)[a.subject]
    norm = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'normalized.json'), None)}
    audit = {r['_id']: r for r in groq_client.load_json(os.path.join(ROOT, 'data', 'audit.json'), None)}
    out_path = os.path.join(ROOT, a.out)
    res = groq_client.load_json(out_path, {})
    ready = [i for i, n in norm.items() if n.get('q_source') != 'pending-vision' and n.get('question_md')]
    if a.ids:
        want = set(groq_client.load_json(os.path.join(ROOT, a.ids), []))
        ready = [i for i in ready if i in want]
    print(f'{len(ready)} questions ready (of {len(norm)}) | tagger {a.version} -> {a.out}')

    # ---- T1: chapter. Batch by the chapter the question was requested for (similar content → shorter reasoning)
    chapters = list(tax)
    if a.version == 'v2':
        chapter_text = '\n'.join(f'- {c}: ' + '; '.join(tax[c]) for c in chapters)
        T1_PROMPT = T1_V2
    else:
        chapter_text = '\n'.join(f'- {c}' for c in chapters)
        T1_PROMPT = T1
    todo = [i for i in ready if 'chapter' not in res.get(i, {})]
    by_req = defaultdict(list)
    for i in todo: by_req[audit[i]['requested_chapter']].append(i)
    n_calls = 0
    for req, ids in by_req.items():
        for b in batches(ids, a.batch):
            if a.max_batches and n_calls >= a.max_batches: break
            n_calls += 1
            pairs = [(f'q{k + 1}', norm[i]) for k, i in enumerate(b)]
            mk = lambda ps: T1_PROMPT.format(subject=a.subject, chapters=chapter_text, questions=qblock(ps))
            try:
                got = run_robust(a.t1_model, mk, pairs, chapters, 'chapter', 'tag-chapter')
            except groq_client.DailyLimit as e:
                print('daily limit:', e); groq_client.save_json(out_path, res); return
            for (qid, _), i in zip(pairs, b):
                if qid in got:
                    res.setdefault(i, {}).update(chapter=got[qid]['chapter'], chapter_conf=got[qid]['confidence'],
                                                 chapter_reason=got[qid]['reason'])
            groq_client.save_json(out_path, res)
            print(f'T1 {req[:28]:28s} +{len(b)}')

    # ---- T2: concept >> sub-concept within the predicted chapter
    todo = [i for i in ready if 'chapter' in res.get(i, {}) and 'subConcept' not in res[i]]
    by_ch = defaultdict(list)
    for i in todo: by_ch[res[i]['chapter']].append(i)
    n_calls = 0
    for ch, ids in by_ch.items():
        if a.max_batches and n_calls >= a.max_batches: break
        pair_list = [f'{co}{SEP}{sub}' for co, subs in tax[ch].items() for sub in subs]
        for b in batches(ids, a.batch):
            if a.max_batches and n_calls >= a.max_batches: break
            n_calls += 1
            pairs = [(f'q{k + 1}', norm[i]) for k, i in enumerate(b)]
            mk = lambda ps, ch=ch, pl=pair_list: T2.format(subject=a.subject, chapter=ch, pairs='\n'.join(f'- {p}' for p in pl),
                                                            questions=qblock(ps))
            try:
                got = run_robust(a.t2_model, mk, pairs, pair_list, 'pair', 'tag-subconcept')
            except groq_client.DailyLimit as e:
                print('daily limit:', e); groq_client.save_json(out_path, res); return
            for (qid, _), i in zip(pairs, b):
                if qid in got:
                    co, sub = got[qid]['pair'].split(SEP, 1)
                    res[i].update(concept=co, subConcept=sub, sub_conf=got[qid].get('confidence'), sub_reason=got[qid].get('reason', ''),
                                  sub_snapped=bool(got[qid].get('snapped')))
            groq_client.save_json(out_path, res)
            print(f'T2 {ch[:28]:28s} +{len(b)}')
    print('tagged:', sum(1 for v in res.values() if 'subConcept' in v), '| chapter only:',
          sum(1 for v in res.values() if 'chapter' in v and 'subConcept' not in v))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
