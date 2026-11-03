"""Deterministic conversion of Acadza question HTML (with inline MathML) to Markdown + LaTeX.

No LLM involved: 350/449 sampled questions store maths as MathML, which maps to LaTeX exactly.
Formula <img> tags are kept as placeholders ([[IMG:n]]) for the vision stage.
"""
import html as htmllib
import re
import xml.etree.ElementTree as ET

MO_MAP = {
    '−': '-', '–': '-', '×': r'\times', '÷': r'\div', '·': r'\cdot', '⋅': r'\cdot', '±': r'\pm', '∓': r'\mp',
    '≤': r'\le', '≥': r'\ge', '≠': r'\ne', '≈': r'\approx', '≡': r'\equiv', '∞': r'\infty', '→': r'\to',
    '⇒': r'\Rightarrow', '⇔': r'\Leftrightarrow', '∈': r'\in', '∉': r'\notin', '⊂': r'\subset', '⊆': r'\subseteq',
    '∪': r'\cup', '∩': r'\cap', '∑': r'\sum', '∏': r'\prod', '∫': r'\int', '∮': r'\oint', '√': r'\sqrt{}',
    '∂': r'\partial', '∇': r'\nabla', '…': r'\ldots', '⋯': r'\cdots', '°': r'^{\circ}', '∠': r'\angle',
    '⊥': r'\perp', '∥': r'\parallel', '∀': r'\forall', '∃': r'\exists', '∅': r'\emptyset', '′': "'",
    '{': r'\{', '}': r'\}', '|': '|', '∣': '|', '‖': r'\|', '⟨': r'\langle', '⟩': r'\rangle', '\u2061': '', '\u2062': '',
    '\u2063': ',', '\u00a0': ' ', '⌊': r'\lfloor', '⌋': r'\rfloor', '⌈': r'\lceil', '⌉': r'\rceil', '%': r'\%',
}
MI_MAP = {
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta', 'ε': r'\varepsilon', 'ϵ': r'\epsilon',
    'θ': r'\theta', 'λ': r'\lambda', 'μ': r'\mu', 'π': r'\pi', 'ρ': r'\rho', 'σ': r'\sigma', 'τ': r'\tau',
    'φ': r'\phi', 'ϕ': r'\phi', 'ω': r'\omega', 'ζ': r'\zeta', 'η': r'\eta', 'κ': r'\kappa', 'ν': r'\nu',
    'ξ': r'\xi', 'ψ': r'\psi', 'χ': r'\chi', 'Δ': r'\Delta', 'Γ': r'\Gamma', 'Θ': r'\Theta', 'Λ': r'\Lambda',
    'Σ': r'\Sigma', 'Φ': r'\Phi', 'Ω': r'\Omega', 'Π': r'\Pi', 'ℝ': r'\mathbb{R}', 'ℕ': r'\mathbb{N}',
    'ℤ': r'\mathbb{Z}', 'ℚ': r'\mathbb{Q}', 'ℂ': r'\mathbb{C}', '…': r'\ldots', '∞': r'\infty',
}
FUNCS = {'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'cosec', 'log', 'ln', 'exp', 'lim', 'max', 'min',
         'sinh', 'cosh', 'tanh', 'det', 'arg', 'gcd'}


def _tag(el):
    return el.tag.split('}')[-1]


def _txt(el):
    return (el.text or '').strip()


def _group(s):
    return s if len(s) == 1 else '{' + s + '}'


_CMD_END = re.compile(r'\\[A-Za-z]+$')


def _op(s):
    """Map an operator; a LaTeX command ending in a letter needs a trailing space, otherwise the next token glues on
    (A∩B -> \\capB, x∈R -> \\inR: undefined commands that KaTeX shows as errors and LLMs read as garbage)."""
    v = MO_MAP.get(s, s)
    return v + ' ' if _CMD_END.search(v) else v


def conv(el):
    t = _tag(el)
    kids = list(el)
    if t in ('math', 'mrow', 'mstyle', 'semantics', 'mpadded', 'mphantom', 'menclose', 'merror'):
        return ''.join(conv(k) for k in kids)
    if t == 'annotation' or t == 'annotation-xml':
        return ''
    if t == 'mi':
        s = _txt(el)
        if s in MI_MAP: return MI_MAP[s] + ' '
        if s in FUNCS: return '\\' + ('csc' if s == 'cosec' else s) + ' '
        if len(s) > 1: return r'\mathrm{' + s + '}'
        return s
    if t == 'mn':
        return _txt(el)
    if t == 'mo':
        s = _txt(el)
        if s in FUNCS: return '\\' + s + ' '
        return _op(s)
    if t == 'mtext':
        s = (el.text or '')
        return r'\text{' + s + '}' if s.strip() else ' '
    if t == 'mspace':
        return r'\,'
    if t == 'msup' and len(kids) == 2:
        return _group(conv(kids[0])) + '^{' + conv(kids[1]) + '}'
    if t == 'msub' and len(kids) == 2:
        return _group(conv(kids[0])) + '_{' + conv(kids[1]) + '}'
    if t == 'msubsup' and len(kids) == 3:
        return _group(conv(kids[0])) + '_{' + conv(kids[1]) + '}^{' + conv(kids[2]) + '}'
    if t == 'mfrac' and len(kids) == 2:
        if el.get('linethickness') in ('0', '0px'):
            return r'\binom{' + conv(kids[0]) + '}{' + conv(kids[1]) + '}'
        return r'\frac{' + conv(kids[0]) + '}{' + conv(kids[1]) + '}'
    if t == 'msqrt':
        return r'\sqrt{' + ''.join(conv(k) for k in kids) + '}'
    if t == 'mroot' and len(kids) == 2:
        return r'\sqrt[' + conv(kids[1]) + ']{' + conv(kids[0]) + '}'
    if t in ('munder', 'mover', 'munderover'):
        base = conv(kids[0]) if kids else ''
        b = base.strip()
        big = b in (r'\sum', r'\prod', r'\int', r'\lim', r'\max', r'\min', r'\bigcup', r'\bigcap')
        if t == 'mover' and len(kids) == 2:
            acc = conv(kids[1]).strip()
            accents = {'→': r'\vec', r'\to': r'\vec', '^': r'\hat', '¯': r'\overline', '‾': r'\overline',
                       '_': r'\overline', '~': r'\tilde', '˙': r'\dot', '.': r'\dot', '⏞': r'\overbrace'}
            if acc in accents: return accents[acc] + '{' + base + '}'
            return (base + '^{' + acc + '}') if big else r'\overset{' + acc + '}{' + base + '}'
        if t == 'munder' and len(kids) == 2:
            u = conv(kids[1])
            return (base + '_{' + u + '}') if big else r'\underset{' + u + '}{' + base + '}'
        if t == 'munderover' and len(kids) == 3:
            return base + '_{' + conv(kids[1]) + '}^{' + conv(kids[2]) + '}'
    if t == 'mfenced':
        o, c = el.get('open', '('), el.get('close', ')')
        sep = el.get('separators', ',')
        inner = (sep[:1] or ',').join(conv(k) for k in kids)
        return r'\left' + (_op(o) if o else '.') + inner + r'\right' + (_op(c) if c else '.')
    if t == 'mtable':
        rows = []
        for tr in kids:
            cells = [conv(td) for td in tr] if _tag(tr) in ('mtr', 'mlabeledtr') else [conv(tr)]
            rows.append(' & '.join(cells))
        return r'\begin{matrix}' + r' \\ '.join(rows) + r'\end{matrix}'
    if t in ('mtr', 'mtd'):
        return ''.join(conv(k) for k in kids)
    return ''.join(conv(k) for k in kids) + (_txt(el) if not kids else '')


def mathml_to_latex(xml):
    # some stored MathML has a bare '<' or '>' as operator text: <mo><</mo>  (invalid XML)
    xml = xml.replace('<mo><</mo>', '<mo>&lt;</mo>').replace('<mo>></mo>', '<mo>&gt;</mo>')
    xml = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)(\w+);',
                 lambda m: htmllib.unescape('&' + m.group(2) + ';'), xml)   # named HTML entities → chars
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    s = conv(root)
    # A literal '<' or '>' in the LaTeX would later be eaten by the HTML tag stripper ("a<0 ... b>" looks like a tag),
    # which silently deleted text between them (found via a corrupted multi-correct question). Use \lt / \gt.
    s = s.replace('<', r'\lt ').replace('>', r'\gt ')
    s = re.sub(r'\\left\(', '(', s); s = re.sub(r'\\right\)', ')', s)
    return re.sub(r'\s{2,}', ' ', s).strip()


IMG_RE = re.compile(r'<img[^>]*src="([^"]+)"[^>]*>', re.I)
MATH_RE = re.compile(r'<math\b.*?</math>', re.S | re.I)


def html_to_markdown(h):
    """Return (markdown_with_latex, image_urls, n_mathml_failures)."""
    if not h:
        return '', [], 0
    images, fails = [], 0

    def img(m):
        images.append(m.group(1)); return f' [[IMG:{len(images)}]] '

    def math(m):
        nonlocal fails
        lx = mathml_to_latex(m.group(0))
        if lx is None:
            fails += 1; return ' [[MATH?]] '
        return f' ${lx}$ ' if lx else ' '

    s = MATH_RE.sub(math, h)
    s = IMG_RE.sub(img, s)
    # HTML <sup>/<sub> outside MathML: attach to the preceding token and wrap in $...$ so it renders as maths
    def supsub(m):
        base, mark, inner = m.group(1), '^' if m.group(2).lower() == 'sup' else '_', re.sub(r'<[^>]+>', '', m.group(3))
        return f'${base}{mark}{{{htmllib.unescape(inner).strip()}}}$'
    s = re.sub(r'([A-Za-z0-9)\]]*)<(sup|sub)>(.*?)</\2>', supsub, s, flags=re.S | re.I)
    s = s.replace('$$', '')   # merge touching inline fragments ($a$$b$ -> $ab$); MathML output is space-padded
    s = re.sub(r'<br\s*/?>|</p>|</div>|</h\d>|</li>|</tr>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = htmllib.unescape(s).replace('\u00a0', ' ')
    s = '\n'.join(' '.join(line.split()) for line in s.split('\n'))
    s = re.sub(r'\n{3,}', '\n\n', s).strip()
    # put each option on its own line
    s = re.sub(r'\s*\((?=[A-D]\)\s)', '\n(', s).strip()
    return s, images, fails
