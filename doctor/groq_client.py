"""Minimal Groq chat client built for a free-tier budget.

- Disk cache keyed by the exact request, so re-runs cost nothing and runs can resume after a daily limit.
- Respects 429 retry-after headers; paces calls to stay under the per-minute token limit.
- Logs every real call's token usage to data/usage.jsonl (the source for cost numbers in the report).
"""
import hashlib, json, os, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'cache')
USAGE = os.path.join(ROOT, 'data', 'usage.jsonl')
URL = 'https://api.groq.com/openai/v1/chat/completions'
TPM_LIMIT = int(os.environ.get('GROQ_TPM', '8000'))


class DailyLimit(Exception):
    """Raised when Groq says the per-day quota is exhausted; callers should stop and resume later."""


class JsonFailed(Exception):
    """Raised when constrained decoding could not produce schema-valid JSON (Groq json_validate_failed)."""


def _key():
    if os.environ.get('GROQ_API_KEY'):
        return os.environ['GROQ_API_KEY']
    with open(os.path.join(ROOT, '.env'), encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('GROQ_API_KEY='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    raise RuntimeError('GROQ_API_KEY not found in env or .env')


_window = []   # (timestamp, tokens) for calls in the last 60s, per process


def _pace(model, est_tokens):
    now = time.time()
    _window[:] = [(t, n, m) for t, n, m in _window if now - t < 60]
    used = sum(n for t, n, m in _window if m == model)
    if used + est_tokens > TPM_LIMIT * 0.9 and _window:
        oldest = min(t for t, n, m in _window if m == model) if any(m == model for _, _, m in _window) else now
        time.sleep(max(0.0, 60 - (now - oldest)) + 0.5)


def chat(model, messages, *, schema=None, schema_name='out', temperature=0, max_tokens=2048,
         reasoning_effort=None, tag='', est_tokens=2000, use_cache=True, json_mode=False):
    """Return (content_str, usage_dict, cached: bool).
    schema -> strict json_schema (constrained decoding); json_mode -> json_object (valid JSON, schema not enforced)."""
    body = {'model': model, 'messages': messages, 'temperature': temperature, 'max_completion_tokens': max_tokens}
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    elif schema is not None:
        body['response_format'] = {'type': 'json_schema',
                                   'json_schema': {'name': schema_name, 'strict': True, 'schema': schema}}
    if reasoning_effort:
        body['reasoning_effort'] = reasoning_effort
    blob = json.dumps(body, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(blob.encode()).hexdigest()
    path = os.path.join(CACHE, h[:2], h + '.json')
    if use_cache and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d['content'], d['usage'], True

    key = _key()
    for attempt in range(8):
        _pace(model, est_tokens)
        req = urllib.request.Request(URL, data=blob.encode(), headers={
            'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'User-Agent': 'qbd/0.1'})
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors='replace')
            if e.code == 429:
                if 'per day' in txt or 'TPD' in txt or 'RPD' in txt:
                    raise DailyLimit(txt[:300])
                wait = float(e.headers.get('retry-after') or 0) or min(60, 2 ** attempt * 3)
                time.sleep(wait + 0.5); continue
            if e.code in (500, 502, 503, 504):
                time.sleep(2 ** attempt); continue
            if e.code == 400 and 'json_validate_failed' in txt:
                raise JsonFailed(txt[:300])
            raise RuntimeError(f'Groq HTTP {e.code}: {txt[:500]}')
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt); continue
    else:
        raise RuntimeError('Groq: too many retries')

    content = resp['choices'][0]['message'].get('content') or ''
    usage = resp.get('usage', {})
    _window.append((time.time(), usage.get('total_tokens', est_tokens), model))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'content': content, 'usage': usage, 'model': model}, f, ensure_ascii=False)
    with open(USAGE, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': time.time(), 'model': model, 'tag': tag, 'latency_s': round(time.time() - t0, 2),
                            'prompt': usage.get('prompt_tokens'), 'completion': usage.get('completion_tokens'),
                            'total': usage.get('total_tokens')}) + '\n')
    return content, usage, False


def save_json(path, obj):
    """Atomic write: other stages may be reading this file concurrently."""
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    for k in range(20):   # Windows refuses to replace a file another process has open for a moment
        try:
            os.replace(tmp, path); return
        except PermissionError:
            time.sleep(0.25 * (k + 1))
    os.replace(tmp, path)


def load_json(path, default):
    err = None
    for _ in range(5):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except json.JSONDecodeError as e:
            err = e; time.sleep(0.5)   # a non-atomic writer from an older run; retry
    raise err


def chat_json(model, messages, schema, retries=2, **kw):
    """Strict-schema call; on json_validate_failed retry with a little temperature (different decode path)."""
    last = None
    for k in range(retries + 1):
        try:
            kw2 = dict(kw, temperature=kw.get('temperature', 0) if k == 0 else 0.3 + 0.2 * k)
            content, usage, cached = chat(model, messages, schema=schema, **kw2)
            return json.loads(content), usage, cached
        except (JsonFailed, json.JSONDecodeError) as e:
            last = e
    raise JsonFailed(str(last))
