"""Run (or resume) every quota-bound stage in order. Safe to re-run: each stage caches calls and skips finished
questions, and stops cleanly when Groq's daily token limit is reached. Run it again later to continue.

Usage: .venv/Scripts/python -I run_all.py
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
STEPS = [
    ('normalize (vision for image-maths questions and solutions)', ['doctor/normalize.py', '--solutions']),
    ('re-tag items hit by the glued-LaTeX bug',       ['doctor/tag_v3.py', '--ids', 'eval/retag_latex_ids.json', '--redo']),
    ('tag v3 on the evaluation set first',            ['doctor/tag_v3.py', '--ids', 'eval/v2_ids.json']),
    ('tag v3 on everything',                          ['doctor/tag_v3.py']),
    ('verify answer keys (frozen stratified sample)', ['doctor/verify.py', '--per-chapter', '20']),
    ('re-verify items hit by the < > bug',            ['doctor/verify.py', '--ids', 'eval/reverify_ids.json']),
    ('re-verify items hit by the glued-LaTeX bug',    ['doctor/verify.py', '--ids', 'eval/reverify_latex_ids.json']),
    ('near-duplicates',                               ['doctor/dedupe.py']),
    ('judge tag disagreements (different model family)', ['eval/judge.py']),
    ('score tagger versions',                         ['eval/compare_taggers.py']),
    ('build REPORT.md',                               ['eval/report.py']),
    ('build app/review.html',                         ['app/build_review.py']),
]

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # Windows consoles default to cp1252
    only_reports = '--reports' in sys.argv
    for name, args in STEPS:
        if only_reports and not args[0].startswith(('eval/compare', 'eval/report', 'app/')):
            continue
        print(f'\n=== {name}', flush=True)
        r = subprocess.run([PY, '-I'] + args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
        tail = (r.stdout or '').strip().splitlines()[-3:]
        print('\n'.join(tail) or '(no output)', flush=True)
        if r.returncode:
            print('stage failed:', (r.stderr or '').strip().splitlines()[-1:], flush=True)
