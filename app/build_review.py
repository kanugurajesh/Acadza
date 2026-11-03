"""Build app/review.html: a self-contained local review screen for the Doctor's proposals.

Embeds Acadza content, so it is written under app/ and git-ignored. Open it directly in a browser.
Usage: python -I app/build_review.py
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'doctor'))
import groq_client
D = lambda *p: os.path.join(ROOT, 'data', *p)


def load(name, default):
    return groq_client.load_json(D(name), default)


def main():
    audit = load('audit.json', []); norm = {r['_id']: r for r in load('normalized.json', [])}
    tags = load('tags_v3.json', {}); ver = load('verify.json', {}); judge = load('judgements.json', {})
    dups = load('duplicates.json', [])
    dup_of = {i: [j for j in g['ids'] if j != i] for g in dups for i in g['ids']}
    items = []
    for r in audit:
        i = r['_id']; n = norm.get(i, {}); t = tags.get(i, {})
        items.append({
            'id': i, 'type': r['type'], 'requested': r['requested_chapter'], 'level': r['level'],
            'flags': r['flags'], 'answer': r['answer'],
            'orig_q': r['question_html'], 'orig_s': r['solution_html'],
            'md_q': n.get('question_md', ''), 'md_s': n.get('solution_md', ''), 'src': n.get('q_source', ''),
            # clean text may be exported only if nothing is left to transcribe and the vision model could read it all
            'md_ok': bool(n.get('question_md')) and n.get('q_source') in ('mathml', 'text', 'vision')
                     and not n.get('q_unreadable') and '[[IMG:' not in n.get('question_md', '')
                     and '[[MATH?]]' not in n.get('question_md', ''),
            'acadza': {'chapter': r['chapter'], 'concept': r['concept'], 'subConcept': r['subConcept']},
            'doctor': {k: t.get(k) for k in ('chapter', 'concept', 'subConcept', 'chapter_conf', 'sub_conf', 'chapter_reason', 'sub_reason')} if t else None,
            'verify': ver.get(i), 'judge': judge.get(i), 'dups': dup_of.get(i, []),
        })
    html = TEMPLATE.replace('/*DATA*/', json.dumps(items, ensure_ascii=False).replace('</', '<\\/'))
    out = os.path.join(ROOT, 'app', 'review.html')
    open(out, 'w', encoding='utf-8').write(html)
    print('wrote', out, len(items), 'questions')


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Question Bank Doctor · Review</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.css">
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.js"></script>
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/contrib/auto-render.min.js"></script>
<style>
:root{--bg:#f6f7f9;--panel:#fff;--ink:#16181d;--mute:#5d6470;--line:#e3e6ea;--accent:#1f5eff;--good:#0f8a4b;--bad:#c2391b;--warn:#b26a00;--chip:#eef1f5}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--panel:#171a20;--ink:#e8eaee;--mute:#9aa2ae;--line:#2a2f38;--accent:#6f9bff;--good:#3fc27e;--bad:#ff7a5c;--warn:#f0b04a;--chip:#222731}}
:root[data-theme=dark]{--bg:#0f1115;--panel:#171a20;--ink:#e8eaee;--mute:#9aa2ae;--line:#2a2f38;--accent:#6f9bff;--good:#3fc27e;--bad:#ff7a5c;--warn:#f0b04a;--chip:#222731}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{display:flex;gap:16px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:2;flex-wrap:wrap}
header h1{font-size:15px;margin:0 8px 0 0}header .stat{color:var(--mute)}
select,input,button{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 8px}
button{cursor:pointer}button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
main{display:grid;grid-template-columns:320px 1fr;min-height:calc(100vh - 56px)}
#list{border-right:1px solid var(--line);overflow:auto;max-height:calc(100vh - 56px)}
.row{padding:9px 12px;border-bottom:1px solid var(--line);cursor:pointer}.row:hover{background:var(--chip)}.row.sel{background:var(--chip);box-shadow:inset 3px 0 var(--accent)}
.row .t{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.row .m{color:var(--mute);font-size:12px}
.chip{display:inline-block;background:var(--chip);border-radius:10px;padding:0 7px;font-size:11px;margin:2px 3px 0 0;color:var(--mute)}
.chip.bad{color:var(--bad)}.chip.good{color:var(--good)}.chip.warn{color:var(--warn)}
#detail{padding:16px;overflow:auto;max-height:calc(100vh - 56px)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:14px}
.card h3{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute)}
.orig{background:#fff;color:#000;border-radius:6px;padding:8px;overflow:auto}.orig h3,.orig p{font:15px/1.6 "Times New Roman",serif;margin:0;color:#000;text-transform:none;letter-spacing:0}
.md{white-space:pre-wrap;font-size:15px;overflow-x:auto}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--mute);font-weight:600;width:120px}
.diff{color:var(--bad);font-weight:600}.same{color:var(--good)}.mute{color:var(--mute)}
.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
@media (max-width:820px){main{grid-template-columns:1fr}#list{max-height:40vh}.cols{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Question Bank Doctor</h1>
<select id="filter"><option value="all">All questions</option><option value="changed">Doctor changes a tag</option><option value="untagged">Acadza untagged</option><option value="off_portion">Off-chapter</option><option value="image">Maths was an image</option><option value="keywrong">Key likely wrong / needs review</option><option value="judged_doctor">Judge: Doctor right</option><option value="judged_acadza">Judge: Acadza right</option><option value="lowconf">Low confidence (&lt;0.7)</option></select>
<input id="q" placeholder="Search text or id" size="22"><span class="stat" id="stat"></span>
<span style="flex:1"></span><button id="export" class="primary">Export accepted fixes</button><button id="theme" title="Toggle theme">◐</button></header>
<main><div id="list"></div><div id="detail"><p class="mute">Select a question.</p></div></main>
<script>
const ITEMS=/*DATA*/;
const KEY='qbd-decisions';let dec={};try{dec=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(dec))}catch(e){}};
const ws=s=>(s||'').split(/\s+/).join(' ').trim().toLowerCase();
const changed=x=>x.doctor&&x.doctor.subConcept&&(ws(x.doctor.chapter)!==ws(x.acadza.chapter)||ws(x.doctor.concept)!==ws(x.acadza.concept)||ws(x.doctor.subConcept)!==ws(x.acadza.subConcept));
const fixable=x=>!!(x.doctor&&x.doctor.subConcept)||x.md_ok;
const esc=s=>(s??'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function match(x,f){if(f==='all')return true;if(f==='changed')return changed(x);if(f==='untagged')return !x.acadza.subConcept;
 if(f==='off_portion')return x.flags.includes('off_portion');if(f==='image')return x.flags.includes('math_as_image_in_question');
 if(f==='keywrong')return x.verify&&['key_likely_wrong','needs_review','unresolved'].includes(x.verify.status);
 if(f==='judged_doctor')return x.judge&&x.judge.verdict==='doctor';if(f==='judged_acadza')return x.judge&&x.judge.verdict==='acadza';
 if(f==='lowconf')return x.doctor&&x.doctor.sub_conf!=null&&x.doctor.sub_conf<0.7;return true}
let sel=null;
function chips(x){let c='';if(!x.acadza.subConcept)c+='<span class="chip warn">untagged</span>';if(x.flags.includes('off_portion'))c+='<span class="chip bad">off-chapter</span>';
 if(x.flags.includes('math_as_image_in_question'))c+='<span class="chip">image maths</span>';if(changed(x))c+='<span class="chip warn">tag change</span>';
 if(x.verify){const s=x.verify.status;c+=`<span class="chip ${s==='key_confirmed'?'good':s==='key_likely_wrong'?'bad':'warn'}">${esc(s)}</span>`}
 if(x.judge)c+=`<span class="chip ${x.judge.verdict==='doctor'?'good':x.judge.verdict==='acadza'?'bad':''}">judge: ${esc(x.judge.verdict)}</span>`;
 if(dec[x.id])c+=`<span class="chip ${dec[x.id]==='accept'?'good':'bad'}">${dec[x.id]}ed</span>`;return c}
function renderList(){const f=document.getElementById('filter').value,q=ws(document.getElementById('q').value);
 const xs=ITEMS.filter(x=>match(x,f)&&(!q||x.id.includes(q)||ws(x.md_q).includes(q)));
 document.getElementById('stat').textContent=`${xs.length} of ${ITEMS.length} · ${Object.values(dec).filter(v=>v==='accept').length} accepted`;
 document.getElementById('list').innerHTML=xs.map(x=>`<div class="row ${x.id===sel?'sel':''}" data-id="${x.id}"><div class="t">${esc((x.md_q||'').replace(/\$/g,'').slice(0,90))}</div><div class="m">${esc(x.requested)} · ${esc(x.type)}</div>${chips(x)}</div>`).join('');
 document.querySelectorAll('.row').forEach(r=>r.onclick=()=>{sel=r.dataset.id;renderList();renderDetail()})}
function cell(a,b){return ws(a)===ws(b)?`<span class="same">${esc(b||'—')}</span>`:`<span class="diff">${esc(b||'—')}</span>`}
function renderDetail(){const x=ITEMS.find(i=>i.id===sel);if(!x)return;const d=x.doctor||{};
 let v='';if(x.verify){const V=x.verify;v=`<div class="card"><h3>Answer key check</h3><table><tr><th>Status</th><td><b>${esc(V.status)}</b> ${esc(V.note||'')}${V.stale?' <span class="chip warn">stale: computed on text with a since-fixed LaTeX bug</span>':''}</td></tr><tr><th>Acadza key</th><td>${esc(JSON.stringify(V.key))}</td></tr><tr><th>gpt-oss-20b</th><td>${esc(JSON.stringify(V.s1&&V.s1.answer))}</td></tr>${V.s2?`<tr><th>gpt-oss-120b</th><td>${esc(JSON.stringify(V.s2.answer))}</td></tr>`:''}${V.s3_solution_says?`<tr><th>Acadza's own solution reaches</th><td>${esc(JSON.stringify(V.s3_solution_says.answer))}</td></tr>`:''}</table></div>`}
 const j=x.judge?`<tr><th>Judge</th><td><b>${esc(x.judge.verdict)}</b> · ${esc(x.judge.reason)}</td></tr>`:'';
 document.getElementById('detail').innerHTML=`
 <div class="card actions"><b>${esc(x.id)}</b><span class="mute">${esc(x.requested)} · ${esc(x.level)} · ${esc(x.type)} · key ${esc(JSON.stringify(x.answer))} · source: ${esc(x.src)}</span><span style="flex:1"></span>
  ${x.md_ok?'':`<span class="chip warn">text not exportable: ${x.src==='pending-vision'?'image maths not transcribed yet':'incomplete or unreadable transcription'}</span>`}
  <button id="acc" class="primary" ${fixable(x)?'':'disabled title="Nothing to export: no Doctor tag and no exportable text"'}>Accept Doctor's fix</button><button id="rej">Keep Acadza's</button></div>
 <div class="cols"><div class="card"><h3>Acadza today (as stored)</h3><div class="orig">${x.orig_q}</div></div>
 <div class="card"><h3>Doctor: clean Markdown + LaTeX</h3><div class="md" id="mdq">${esc(x.md_q)}</div></div></div>
 <div class="card"><h3>Tags</h3><table><tr><th></th><td class="mute">Acadza</td><td class="mute">Doctor (v3)</td><td class="mute">Why</td></tr>
 <tr><th>Chapter</th><td>${esc(x.acadza.chapter||'—')}</td><td>${cell(x.acadza.chapter,d.chapter)} <span class="mute">${d.chapter_conf??''}</span></td><td class="mute">${esc(d.chapter_reason||'')}</td></tr>
 <tr><th>Concept</th><td>${esc(x.acadza.concept||'—')}</td><td>${cell(x.acadza.concept,d.concept)}</td><td></td></tr>
 <tr><th>Sub-concept</th><td>${esc(x.acadza.subConcept||'—')}</td><td>${cell(x.acadza.subConcept,d.subConcept)} <span class="mute">${d.sub_conf??''}</span></td><td class="mute">${esc(d.sub_reason||'')}</td></tr>${j}
 ${x.dups.length?`<tr><th>Duplicates</th><td colspan="3">${x.dups.map(esc).join(', ')}</td></tr>`:''}</table></div>${v}
 <div class="cols"><div class="card"><h3>Acadza solution</h3><div class="orig">${x.orig_s||'<i>none</i>'}</div></div><div class="card"><h3>Solution, clean</h3><div class="md" id="mds">${esc(x.md_s)}</div></div></div>`;
 if(window.renderMathInElement){['mdq','mds'].forEach(id=>renderMathInElement(document.getElementById(id),{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false}))}
 document.getElementById('acc').onclick=()=>{dec[x.id]='accept';save();renderList()};document.getElementById('rej').onclick=()=>{dec[x.id]='reject';save();renderList()}}
document.getElementById('filter').onchange=renderList;document.getElementById('q').oninput=renderList;
document.getElementById('theme').onclick=()=>{const r=document.documentElement;r.dataset.theme=r.dataset.theme==='dark'?'light':'dark'};
document.getElementById('export').onclick=()=>{let held=0;
 const patch=ITEMS.filter(x=>dec[x.id]==='accept'&&fixable(x)).map(x=>{const p={_id:x.id};
  if(x.doctor&&x.doctor.subConcept)Object.assign(p,{chapter:x.doctor.chapter,concept:x.doctor.concept,subConcept:x.doctor.subConcept,tagByAI:true});
  if(x.md_ok)p.questionMarkdown=x.md_q;else held++;return p});
 if(!patch.length){alert('No accepted fixes to export.');return}
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(patch,null,1)],{type:'application/json'}));a.download='acadza_tag_patch.json';a.click();
 if(held)alert(`Exported ${patch.length} fixes. ${held} of them carry tags only: their clean text is incomplete (image maths not transcribed, or unreadable), so it was left out.`)};
renderList();
</script></body></html>"""

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
