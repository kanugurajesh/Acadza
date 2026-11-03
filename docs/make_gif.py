"""Stitch docs/frames/*.png (from capture_screens.js) into docs/img/demo.gif with a caption bar per step.

Frame files are named NNN_<hold ms>.png. Usage: .venv/Scripts/python -I docs/make_gif.py
"""
import glob, os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
WIDTH = 1100
CAPTIONS = [
    '449 real questions, each with its flags',
    '1 · Filter: questions served in an assignment for a different chapter',
    '2 · Acadza as stored (left) vs the clean Markdown + LaTeX the Doctor produced (right)',
    '3 · New tag drawn only from Acadza\'s syllabus, with the reason and a different-model judge',
    '4 · A teacher accepts the fix with one click',
    '5 · Maths stored as images, now transcribed to LaTeX; an untagged question gets a sub-concept',
    '6 · Accepted',
    '7 · Answer-key check: two models disagree with the key; a hand check found two correct options',
    '8 · Export accepted fixes as a patch in Acadza\'s own fields (chapter, concept, subConcept, tagByAI)',
]


def font(size):
    for f in ('C:/Windows/Fonts/segoeuib.ttf', 'C:/Windows/Fonts/arialbd.ttf', '/System/Library/Fonts/Helvetica.ttc'):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def main():
    files = sorted(glob.glob(os.path.join(HERE, 'frames', '*.png')))
    assert files, 'run node docs/capture_screens.js first'
    f = font(19)
    frames, durations = [], []
    for i, path in enumerate(files):
        im = Image.open(path).convert('RGB')
        im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
        bar = 46
        canvas = Image.new('RGB', (im.width, im.height + bar), (22, 24, 29))
        canvas.paste(im, (0, bar))
        ImageDraw.Draw(canvas).text((16, bar // 2), CAPTIONS[i] if i < len(CAPTIONS) else '', font=f,
                                    fill=(255, 255, 255), anchor='lm')
        frames.append(canvas.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE))
        durations.append(int(os.path.basename(path).split('_')[1].split('.')[0]))
    out = os.path.join(HERE, 'img', 'demo.gif')
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print('wrote', out, f'{os.path.getsize(out) / 1e6:.1f} MB,', len(frames), 'frames')


if __name__ == '__main__':
    main()
