#!/usr/bin/env python3
"""Prepare one locally cached Web image per general-catalogue reference.

Image search results are staged in /home/user/image-search by the image_search tool.
The selected files are normalized onto clean white cards; generic catalogue entries
are tagged as indicative (not exact model / brand proof).
"""
from pathlib import Path
import json, re
from PIL import Image, ImageOps, ImageChops

ROOT = Path(__file__).resolve().parent
SEARCH = Path('/home/user/image-search')
OUT = ROOT / 'assets' / 'catalogue'
OUT.mkdir(parents=True, exist_ok=True)

# Prefer the better-focused follow-up search when a first search was off-target.
PREFER = {
    'PAP-006':'cahier-100-pages-grands-carreaux-product-1.jpg',
    'PAP-004':'pap-004-white-paper-a3-80-gsm-ream-500-s-1.jpg',
    'PAP-007':'pap-007-cahier-grands-carreaux-200-pages-1.png',
    'PAP-009':'pap-009-cahier-scolaire-480-pages-double-1.jpg',
    'PAP-015':'pap-015-post-it-notes-76-x-76-mm-3-x-3-i-1.jpg',
    'PAP-019':'pap-019-plastic-spiral-binding-combs-coi-1.jpg',
    'PAP-022':'pap-022-colored-school-chalk-box-product-1.jpg',
    'CLA-001':'cla-001-manila-cardboard-file-folder-a4--1.jpg',
    'CLA-002':'cardboard-string-tie-file-folder-a4-docu-1.jpg',
    'CLA-009':'accordion-file-organizer-13-pocket-a4-ex-1.jpg',
    'CLA-012':'cla-012-cardboard-file-folder-inside-fil-1.jpg',
    'TAB-012':'flip-chart-easel-tripod-stand-legs-with--1.jpg',
    'TAB-013':'roll-up-banner-85-x-200-cm-graphic-stand-1.png',
    'TAB-015':'a1-poster-print-sample-poster-board-prod-1.jpg',
    'ACC-001':'logitech-k120-french-azerty-keyboard-whi-1.webp',
    'ACC-005':'acc-005-simple-black-rectangular-mouse-p-1.jpg',
    'ACC-007':'acc-007-32gb-usb-flash-drive-product-pho-1.png',
    'ACC-010':'2-metre-hdmi-cable-black-product-photo-6-1.jpg',
    'ACC-016':'1080p-webcam-usb-product-photo-isolated--1.jpg',
    'ECR-006':'sharpie-black-permanent-marker-box-of-12-1.jpg',
    'EQP-001':'eqp-001-office-desk-stapler-single-produ-1.jpg',
    'EQP-006':'swingline-two-hole-punch-office-hole-pun-1.jpg',
    'EQP-010':'eqp-010-30-cm-plastic-ruler-office-produ-1.jpg',
    'EQP-011':'eqp-011-office-stamp-pad-rectangular-ink-1.jpg',
    'EQP-015':'scotch-magic-tape-19-mm-office-transpare-1.jpg',
    'EQP-016':'eqp-016-brown-packaging-tape-50-mm-roll--1.jpg',
    'EQP-020':'silver-metal-medium-size-paper-clips-33m-1.jpg',
    'EQP-021':'large-metal-paper-clips-giant-jumbo-pape-1.jpg',
    'EQP-023':'double-a-alkaline-aa-battery-four-pack-d-1.jpg',
    'EPI-007':'ffp2-dust-mask-box-of-20-product-on-whit-1.jpg',
    'EPI-009':'epi-009-orange-high-visibility-vest-full-1.webp',
    'HYG-006':'hyg-006-household-multipurpose-cleaning--1.jpg',
    'INF-006':'inf-006-hp-203a-cf540a-genuine-black-ton-1.png',
    'INF-010':'hp-laserjet-cf284a-84a-black-original-to-1.jpg',
    'MOB-003':'l-shape-office-desk-120cm-product-photo--1.jpg',
    'MOB-006':'metal-filing-cabinet-tall-wardrobe-two-d-1.jpg',
    'ORD-007':'14-inch-business-laptop-intel-core-i5-16-1.jpg',
    'ORD-012':'15-6-inch-laptop-bag-briefcase-black-pro-1.jpg',
}

# The catalogue remains the source of product data; only its photo metadata is enriched here.
data = json.loads((ROOT/'data'/'catalog.json').read_text())
products = [p for p in data['products'] if p['source']=='catalogue']
missing=[]
prepared=0
for p in products:
    ref=p['ref']; candidate=None
    if ref in PREFER:
        f=SEARCH/PREFER[ref]
        if f.exists(): candidate=f
    if candidate is None:
        matches=sorted(SEARCH.glob(ref.lower()+'-*'), key=lambda f:f.stat().st_mtime)
        if matches: candidate=matches[-1]
    if candidate is None:
        missing.append(ref); continue
    try:
        with Image.open(candidate) as src:
            opened=ImageOps.exif_transpose(src)
            if 'A' in opened.getbands() or 'transparency' in opened.info:
                rgba=opened.convert('RGBA'); bg=Image.new('RGBA',rgba.size,(255,255,255,255)); bg.alpha_composite(rgba); im=bg.convert('RGB')
            else:
                im=opened.convert('RGB')
            # Trim excess white canvas around retail product cutouts, while keeping a safe margin.
            diff=ImageChops.difference(im,Image.new('RGB',im.size,(255,255,255))).convert('L')
            bbox=diff.point(lambda v:255 if v>22 else 0).getbbox()
            if bbox:
                x0,y0,x1,y1=bbox; w=x1-x0; h=y1-y0
                pad=max(10,int(max(w,h)*0.055))
                bbox=(max(0,x0-pad),max(0,y0-pad),min(im.width,x1+pad),min(im.height,y1+pad))
                im=im.crop(bbox)
            # Clean display framing: retain the complete product on white, without stretching.
            im.thumbnail((760,560), Image.Resampling.LANCZOS)
            canvas=Image.new('RGB',(800,600),(255,255,255))
            x=(800-im.width)//2; y=(600-im.height)//2
            canvas.paste(im,(x,y))
            final=canvas
            dest=OUT/f'{ref}.jpg'
            final.save(dest,'JPEG',quality=88,optimize=True,progressive=True)
        p['photo']=f'/assets/catalogue/{ref}.jpg'
        p['photoKind']='photo Web indicative'
        p['photoSource']='https://www.google.com/search?tbm=isch&q='+__import__('urllib.parse').parse.quote(p['name']+' '+p['family'])
        p['photoSourceKind']='image_search'
        p['photoNote']='Image Web illustrative du type de produit; elle ne confirme pas une marque, une référence fabricant, une variante ou un conditionnement.'
        prepared+=1
    except Exception as e:
        missing.append(ref)
        print('IMAGE ERROR',ref,candidate,e)

print(f'prepared {prepared}/{len(products)} individual catalogue images')
print(f'missing refs: {missing}')
print('output:',OUT)
