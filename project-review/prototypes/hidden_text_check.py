# Prototype used in this review: render-vs-extract ink check. Usage: python -I hidden_text_check.py <sentinel/datasets dir>
# Measured on the 9 repo fixtures (commit 84bf25f): hidden_text 95 chars, white_on_white 53, suspicious_font_sizes 12, all others 0.
import sys, glob, os, time, pdfplumber, pypdfium2 as pdfium, numpy as np
SCALE=2.0
def analyse(f):
    t=time.time()
    doc=pdfium.PdfDocument(f); page=doc[0]
    img=np.asarray(page.render(scale=SCALE, grayscale=True).to_pil())
    H,W=img.shape
    out={'visible':[], 'hidden':[]}
    with pdfplumber.open(f) as pdf:
        p=pdf.pages[0]
        for c in p.chars:
            if not c['text'].strip(): continue
            x0,x1=int(c['x0']*SCALE),int(c['x1']*SCALE)+1
            y0,y1=int(c['top']*SCALE),int(c['bottom']*SCALE)+1
            off = x1<=0 or y1<=0 or x0>=W or y0>=H
            box=img[max(0,y0):min(H,y1), max(0,x0):min(W,x1)]
            ink = (box<200).mean() if box.size else 0.0
            tiny = c['size']<4
            vis = (not off) and ink>0.02 and not tiny
            out['visible' if vis else 'hidden'].append(c['text'])
    return ''.join(out['hidden']), len(out['visible']), time.time()-t
for f in sorted(glob.glob(sys.argv[1]+'/*/*.pdf')):
    hid,nv,dt=analyse(f)
    print(f"{os.path.basename(f):28s} visible_chars={nv:4d} hidden={len(hid):3d} {dt*1000:.0f}ms  {hid[:70]!r}")
