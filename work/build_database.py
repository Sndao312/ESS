from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from PIL import Image as PILImage
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.comments import Comment
from openpyxl.drawing.image import Image as XLImage
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.dimensions import ColumnDimension

ROOT = Path('/home/user')
IMG_DIR = ROOT / 'image-search'
WORK = ROOT / 'work'
THUMBS = WORK / 'thumbs'
THUMBS.mkdir(parents=True, exist_ok=True)
OUT = ROOT / 'BDD_Cartouches_ESS_2026.xlsx'

# Transcription des lignes du PDF « Prix imprimante.pdf ».
# Les numéros 53 et 54 n'apparaissent pas dans la source.
raw = [
    (1, 'HP85A', 3500), (2, 'HP83A', 3500), (3, 'HP35A', 4000), (4, 'HP36', 4000),
    (5, 'HP78A', 4000), (6, 'HP79A', 4500), (7, 'HP05A', 5000), (8, 'HP12A', 4000),
    (9, 'HP106A', 6000), (10, 'HP107A', 6000), (11, 'HP135A', 13000), (12, 'HP26A', 8000),
    (13, 'HP44A', 5000), (14, 'HP201N', 7500), (15, 'HP201C', 7500), (16, 'HP80A', 5000),
    (17, 'HP90A', 17000), (18, 'HP17A', 5000), (19, 'HP30A', 6000), (20, 'HP150A', 9000),
    (21, 'HP151A', 14000), (22, 'HP59A', 15000), (23, 'HP205N', 7500), (24, 'HP205C', 7500),
    (25, 'HP203N', 7500), (26, 'HP203C', 7500), (27, 'HP206N', 14000), (28, 'HP206C', 14000),
    (29, 'HP207N', 13000), (30, 'HP207C', 13000), (31, 'HP216N', 11000), (32, 'HP216C', 11000),
    (33, 'HP230N', 18000), (34, 'HP230C', 18000), (35, 'HP222N', 18000), (36, 'HP222C', 18000),
    (37, 'HP125N', 7500), (38, 'HP125C', 7500), (39, 'HP131N', 7500), (40, 'HP131C', 7500),
    (41, 'HP126N', 7000), (42, 'HP126C', 7000), (43, 'HP130N', 7000), (44, 'HP130C', 7500),
    (45, 'HP131N', 7500), (46, 'HP131C', 7500),
    (47, 'HP117N', 9000), (48, 'HP117C', 9000), (49, 'HP410N', 7500), (50, 'HP410C', 7500),
    (51, 'HP415N', 14000), (52, 'HP415C', 14000),
    (55, 'HP305N', 7500), (56, 'HP305C', 7500), (57, 'HP312N', 7500), (58, 'HP312C', 7500),
    (59, 'HP304N', 9000), (60, 'HP304C', 9000), (61, 'HP44A', 5500), (62, 'HP81A', 20000),
    (63, 'HP147A', 25000), (64, 'HP55A', 13000), (65, 'TAMB19A', 8000), (66, 'TAMB120A', 20000),
    (67, 'CANON045N', 7500), (68, 'CANON045C', 7500), (69, 'CANON055N', 13000), (70, 'CANON055C', 13000),
    (71, 'CANON067N', 13000), (72, 'CANON067C', 13000), (73, 'CANON069N', 14000), (74, 'CANON069C', 14000),
    (75, 'CANON070', 14000), (76, 'CANON071', 13000), (77, 'CANON725', 3800), (78, 'CANON719', 5000),
    (79, 'CANN047', 20000), (80, 'CANON052', 9000), (81, 'CANON057', 13000), (82, 'CANON728', 4000),
    (83, 'CEXVV28N', 17000), (84, 'CEXV28C', 17000), (85, 'CEXV29N', 17000), (86, 'CEXV29C', 17000),
    (87, 'CEXV33', 4000), (88, 'CEXV42', 4000), (89, 'CEXV54', 15000), (90, 'CEXV60', 4000),
    (91, 'CEXV65', 19000), (92, 'CEXV54C', 15000),
    (93, 'CEXV42GIGA', None), (94, 'CEXV33GIGA', None), (95, 'CEXV65GIGA', None), (96, 'CEXV64', None),
    (97, 'CEXV59', None), (98, 'CEXV59GIGA', None), (99, 'CEXV37', None), (100, 'CEXV34', None),
    (101, 'GR15', None), (102, 'GPR18', None),
]
assert len(raw) == 100, f'Attendu 100 lignes source, trouvé {len(raw)}'

# Visuels de recherche Web. Les images ne prouvent pas l'authenticité ou le stock réel.
# Le statut précise les correspondances de famille ou d'équivalence à vérifier.
photo_map = {
    'HP85A': ('genuine-hp-85a-ce285a-original-toner-car-1.webp', 'https://www.hp.com/my-en/shop/hp-85a-black-original-laserjet-toner-cartridge-ce285a.html', 'Photo du modèle fabricant HP 85A / CE285A.'),
    'HP83A': ('genuine-original-hp-83a-cf283a-toner-car-1.jpg', 'https://www.ebay.com/itm/336339590869', 'Photo du modèle HP 83A / CF283A; annonce indiquée Genuine.'),
    'HP35A': ('genuine-original-hp-35a-cb435a-toner-car-1.jpg', 'https://ebay.com/p/1431442498', 'Photo HP 35A / CB435A, annoncée Genuine OEM.'),
    'HP36': ('hp-36a-cb436a-genuine-original-hp-laserj-1.jpg', 'https://www.ebay.com/p/1682538357', 'Visuel HP 36A / CB436A; le PDF indique HP36 sans suffixe A.'),
    'HP78A': ('genuine-original-hp-78a-ce278a-toner-car-1.jpg', 'https://ebay.com/p/1551242964', 'Photo HP 78A / CE278A.'),
    'HP79A': ('hp-79a-cf279a-genuine-original-hp-laserj-1.png', 'https://inkgenie.com/products/genuine-hp-79a-cf279a-black-laserjet-toner-cartridge', 'Photo HP 79A / CF279A, annoncé Genuine.'),
    'HP05A': ('hp-05a-ce505a-original-genuine-black-ton-1.jpg', 'https://technomartllc.com/hp-05a-ce505a-black-original-laserjet-toner-cartridge/', 'Photo HP 05A / CE505A original.'),
    'HP12A': ('hp-12a-q2612a-black-original-laserjet-to-1.jpg', 'https://ebay.com/p/1340049931', 'Photo HP 12A / Q2612A, annoncée Genuine OEM Original.'),
    'HP106A': ('hp-106a-w1106a-original-genuine-hp-toner-1.png', 'https://btech.com/en/p/hp-106a-laser-cartridge-black-w1106a', 'Visuel trouvé sous HP 106A / W1106A; vérifier le conditionnement réel.'),
    'HP107A': ('genuine-original-hp-107a-w1107a-toner-ca-1.jpg', 'https://coloursoft.co.ke/shop/toner/hp-toner/hp-107a-toner-by-coloursoft-3-year-warranty/', 'Photo HP 107A / W1107A.'),
    'HP135A': ('genuine-original-hp-135a-w1350a-toner-ca-1.jpg', 'https://ebay.co.uk/p/4065856340', 'Photo HP 135A / W1350A; série 135A.'),
    'HP26A': ('genuine-original-hp-26a-cf226a-toner-car-1.png', 'https://www.ebay.com/itm/366549025003', 'Photo HP 26A / CF226A.'),
    'HP44A': ('genuine-original-hp-44a-toner-cartridge--1.webp', 'https://aridvalok.com/product/hp-44a-black-original-laserjet-toner-cartridge-cf244a/', 'Photo HP 44A / CF244A.'),
    'HP201N': ('genuine-original-hp-201n-201a-cf400a-ton-1.jpg', 'https://www.ebay.com/itm/286253569168', 'Visuel HP 201A noire / CF400A (suffixe N de la source interprété Noir).'),
    'HP201C': ('genuine-original-hp-201c-201a-cf401a-ton-1.png', 'https://inkgenie.com/products/genuine-hp-201a-cyan-cf401a-laserjet-toner-cartridge', 'Visuel HP 201A Cyan / CF401A (suffixe C de la source interprété Cyan).'),
    'HP80A': ('hp-80a-cf280a-original-genuine-hp-laserj-1.jpg', 'https://www.ebay.com/itm/167293535015', 'Photo HP 80A / CF280A; emballage illustré, vérifier le lot réel.'),
    'HP90A': ('hp-90a-ce390a-black-original-genuine-ton-1.jpg', 'https://www.ebay.com/p/25037500769', 'Photo HP 90A / CE390A; annonce Genuine, boîte ouverte.'),
    'HP17A': ('hp-17a-cf217a-genuine-original-hp-toner--1.jpg', 'https://www.ebay.com/itm/224347747218', 'Photo HP 17A / CF217A, Genuine OEM Original.'),
    'HP30A': ('hp-30a-cf230a-original-genuine-hp-toner--1.jpg', 'https://ebay.com/p/17021690987', 'Photo HP 30A / CF230A.'),
    'HP150A': ('genuine-original-hp-150a-w1500a-toner-ca-1.jpg', 'https://coloursoft.co.ke/shop/toner/hp-toner/original-genuine-hp-150a-toner-cartridge-w1500a/', 'Photo HP 150A / W1500A.'),
    'HP151A': ('genuine-original-hp-151a-toner-cartridge-1.jpg', 'https://coloursoft.co.ke/shop/toner/hp-toner/genuine-original-hp-151a-toner-cartridge-w1510a/', 'Photo HP 151A / W1510A.'),
    'HP59A': ('hp-59a-cf259a-original-hp-genuine-black--1.jpg', 'https://ebay.com/p/21042490784', 'Photo HP 59A / CF259A, Genuine.'),
    'HP205N': ('hp-205a-cf530a-genuine-original-black-to-1.jpg', 'https://cartridgemasters.net/shop/hp-205a-black-toner-cartridge-1100-pages-original-cf530a-single-pack/', 'Visuel HP 205A noire / CF530A (suffixe N de la source interprété Noir).'),
    'HP205C': ('hp-205a-cf531a-original-genuine-hp-cyan--1.jpg', 'https://www.ebay.co.uk/p/14008877033', 'Visuel HP 205A Cyan / CF531A (suffixe C interprété Cyan).'),
    'HP203N': ('hp-203a-cf540a-original-genuine-hp-black-1.jpg', 'https://ebay.co.uk/p/2305807448', 'Visuel HP 203A noire / CF540A (suffixe N interprété Noir).'),
    'HP203C': ('hp-203a-cf541a-original-genuine-hp-cyan--1.jpg', 'https://ebay.co.uk/p/2267689989', 'Visuel HP 203A Cyan / CF541A (suffixe C interprété Cyan).'),
    'HP206N': ('genuine-original-hp-206n-black-toner-car-1.jpg', 'https://www.ebay.com/p/14039156104', 'Visuel HP 206A noire / W2110A (suffixe N interprété Noir).'),
    'HP206C': ('genuine-original-hp-206c-cyan-toner-cart-1.jpg', 'https://ebay.com/p/10039160665', 'Visuel HP 206A Cyan (suffixe C interprété Cyan).'),
    'HP207N': ('genuine-original-hp-207n-black-toner-car-1.webp', 'https://www.ebay.com/itm/387355003946', 'Visuel HP 207A noire / W2210A.'),
    'HP207C': ('hp-207a-w2211a-genuine-original-cyan-ton-1.jpg', 'https://www.makingitgreen.co.uk/hp-cyan-toner-cartridge-207a-w2211a/', 'Visuel HP 207A Cyan / W2211A.'),
    'HP216N': ('hp-216a-genuine-original-black-toner-car-1.webp', 'https://www.ebay.com/itm/275779125262', 'Visuel HP 216A noire / W2410A.'),
    'HP216C': ('hp-216a-genuine-original-cyan-toner-cart-1.jpg', 'https://www.dabbousmega.com/products/hp-216a-original-toner', 'Visuel HP 216A Cyan.'),
    'HP230N': ('hp-230a-genuine-original-black-toner-car-1.jpg', 'https://ltonlinestore.com/HP-230A-Black-LaserJet-Toner-Cartridge-W2300A-p600111506', 'Visuel HP 230A noire / W2300A.'),
    'HP230C': ('hp-230a-genuine-original-cyan-toner-cart-1.png', 'https://lionperu.com/producto/hp-230a-cyan-toner-w2301a-original-laserjet-toner-cartridge-precio-cartucho', 'Visuel HP 230A Cyan / W2301A.'),
    'HP222N': ('hp-222a-genuine-original-black-toner-car-1.jpg', 'https://www.indiamart.com/proddetail/hp-222a-black-original-laserjet-toner-cartridge-2856279417748.html', 'Visuel HP 222A noire.'),
    'HP222C': ('hp-222a-genuine-original-cyan-toner-cart-1.jpg', 'https://www.indiamart.com/proddetail/hp-222a-cyan-original-laserjet-toner-cartridge-w2221a-2856279462530.html', 'Visuel HP 222A Cyan / W2221A.'),
    'HP125N': ('genuine-original-hp-125n-black-toner-car-1.jpg', 'https://www.ebay.com/p/3011036922', 'Visuel HP 125A noire / CB540A.'),
    'HP125C': ('genuine-original-hp-125c-cyan-toner-cart-1.jpg', 'https://ebay.com/p/1224598654', 'Visuel HP 125A Cyan / CB541A.'),
    'HP131N': ('hp-131a-cf210a-genuine-original-black-to-1.jpg', 'https://www.officedepot.com/a/products/829348/HP-131A-Black-Toner-Cartridge-CF210A/', 'Visuel HP 131A noire / CF210A.'),
    'HP131C': ('genuine-original-hp-131c-cyan-toner-cart-1.jpg', 'https://ebay.com/p/140922286', 'Visuel HP 131A Cyan / CF211A.'),
    'HP126N': ('hp-126a-ce310a-genuine-original-black-to-1.jpg', 'https://ebay.com/itm/177133615764', 'Visuel HP 126A noire / CE310A.'),
    'HP126C': ('hp-126a-ce311a-genuine-original-cyan-ton-1.png', 'https://www.hp.com/us-en/shop/standard-capacity-toner-cartridges/hp-126a-cyan-original-laserjet-toner-cartridge', 'Visuel HP 126A Cyan / CE311A.'),
    'HP130N': ('hp-130a-cf350a-genuine-original-black-to-1.jpg', 'https://www.officedepot.com/a/products/345134/HP-130A-Black-Toner-Cartridge-CF350A/', 'Visuel HP 130A noire / CF350A.'),
    'HP130C': ('hp-130a-cf351a-cyan-original-genuine-hp--1.jpg', 'https://ebay.com/p/710189550', 'Visuel HP 130A Cyan / CF351A.'),
    'HP117N': ('hp-117a-w2070a-black-original-genuine-hp-1.webp', 'https://pccircle.com/product/hp-117a-black-original-laser-toner-cartridge-w2070a/', 'Visuel HP 117A noire / W2070A.'),
    'HP117C': ('hp-117a-w2071a-genuine-original-cyan-ton-1.jpg', 'https://www.ebay.co.uk/itm/358546304534', 'Visuel HP 117A Cyan / W2071A.'),
    'HP410N': ('hp-410a-cf410a-genuine-original-black-to-1.jpg', 'https://www.ebay.com/p/14026724823', 'Visuel HP 410A noire / CF410A.'),
    'HP410C': ('hp-410a-cf411a-genuine-original-cyan-ton-1.jpg', 'https://toner-inkjet.com/HP-410A-Cyan-Toner-Cartridge-CF411A-Original', 'Visuel HP 410A Cyan / CF411A.'),
    'HP415N': ('hp-415a-w2030a-genuine-original-black-to-1.jpg', 'https://ebay.co.uk/p/25032772454', 'Visuel HP 415A noire / W2030A.'),
    'HP415C': ('hp-415a-w2031a-genuine-original-cyan-ton-1.png', 'https://www.firstshop.co.za/products/hp-415a-cyan-toner-cartridge-2-100-pages-original-w2031a-single-pack-88898', 'Visuel HP 415A Cyan / W2031A.'),
    'HP305N': ('hp-305a-ce410a-genuine-original-black-to-1.jpg', 'https://www.ebay.com/p/10033160524', 'Visuel HP 305A noire / CE410A.'),
    'HP305C': ('hp-305a-ce411a-original-hp-cyan-toner-ca-1.jpg', 'https://www.ebay.com/p/10012050093', 'Visuel HP 305A Cyan / CE411A.'),
    'HP312N': ('hp-312a-black-toner-cartridge-genuine-or-1.jpg', 'https://ebay.com/p/1880905404', 'Visuel HP 312A noire / CF380A.'),
    'HP312C': ('hp-312a-cyan-toner-cartridge-genuine-ori-1.jpg', 'https://ebay.com/p/2254487957', 'Visuel HP 312A Cyan / CF381A.'),
    'HP304N': ('hp-304a-cc530a-original-hp-black-toner-c-1.jpg', 'https://www.ebay.com/p/85597587', 'Visuel HP 304A noire / CC530A.'),
    'HP304C': ('hp-304a-cc531a-genuine-original-cyan-ton-1.jpg', 'https://ebay.com/p/710152125', 'Visuel HP 304A Cyan / CC531A.'),
    'HP81A': ('hp-81a-ce401a-original-genuine-imaging-d-1.jpg', 'https://ebay.com/p/1639381823', 'Visuel HP 81A noire / CF281A (référence fabricant associée).'),
    'HP147A': ('hp-147a-w1470a-genuine-original-hp-toner-1.jpg', 'https://ebay.com/p/16039874041', 'Visuel HP 147A / W1470A, annoncée Genuine Original.'),
    'HP55A': ('hp-55a-ce255a-original-genuine-hp-black--1.jpg', 'https://www.officecrave.com/hp-ce255a.html', 'Photo HP 55A / CE255A original.'),
    'TAMB19A': ('toner-drum-tamb19a-genuine-original-prod-1.jpg', 'https://ebay.com/p/747446709', 'Visuel tambour HP 19A / CF219A; code TAMB19A à valider.'),
    'TAMB120A': ('toner-drum-tamb120a-genuine-original-pro-1.jpg', 'https://www.amazon.com/HP-120A-W1120A-Toner-Cartridge/dp/B07QLCS8VM', 'Visuel tambour HP 120A / W1120A; code TAMB120A à valider.'),
    'CANON045N': ('canon-045-n-black-original-genuine-toner-1.png', 'https://www.ebay.com/itm/356592606158', 'Visuel de la gamme Canon 045 Genuine, boîte 4 couleurs; pas une photo isolée du noir.'),
    'CANON045C': ('genuine-canon-045-cyan-toner-cartridge-1-1.jpg', 'https://ebay.com/p/3031097777', 'Photo Canon 045 Cyan / 1241C001.'),
    'CANON055N': ('genuine-canon-055-black-toner-cartridge--1.jpg', 'https://amazon.com/clp/B08D9DYLS2', 'Photo Canon Genuine 055 Black / 3016C001.'),
    'CANON055C': ('canon-055-cyan-3015c001-genuine-oem-orig-1.png', 'https://officedepot.com/a/products/5620467/Canon-055-Cyan-Toner-Cartridge-3015C001/', 'Photo Canon 055 Cyan / 3015C001.'),
    'CANON067N': ('canon-067-5102c001-genuine-original-oem--1.jpg', 'https://www.ebay.com/p/23058878108', 'Photo Canon 067 Black / 5102C001.'),
    'CANON067C': ('canon-067-5101c001-genuine-original-oem--1.jpg', 'https://ebay.com/p/20064758074', 'Photo Canon 067 Cyan / 5101C001.'),
    'CANON069N': ('canon-069-n-black-original-genuine-toner-1.jpg', 'https://www.247inktoner.com/canon-069-black-toner-cartridge-5094c001-genuine-oem', 'Photo Canon 069 Black / 5094C001, Genuine OEM.'),
    'CANON070': ('genuine-canon-070-toner-cartridge-5639c0-1.jpg', 'https://www.officedepot.com/a/products/9798294/Canon-070-Black-Toner-Cartridge-5639C001/', 'Photo Canon 070 Black / 5639C001.'),
    'CANON071': ('genuine-canon-071-toner-cartridge-5645c0-1.jpg', 'https://ebay.com/p/9063656199', 'Photo Canon 071 / 5645C001.'),
    'CANON725': ('canon-725-genuine-original-toner-cartrid-1.png', 'https://itubia.com/products/canon-725-original-black-toner-cartridge', 'Photo Canon 725 noire originale / 3484B002.'),
    'CANON719': ('canon-719-black-toner-cartridge-3479b001-1.jpg', 'https://ebay.com/itm/376395955585', 'Visuel Canon 119 / 3479B001, équivalence de gamme 719 à vérifier.'),
    'CANN047': ('canon-047-2164c001-original-genuine-cano-1.jpg', 'https://www.inkjetsuperstore.ca/p-380938-canon-047-oem-canon-047-2164c001aa-original-black-toner-cartridge', 'Photo Canon 047 / 2164C001; code source CANN047 à vérifier.'),
    'CANON057': ('canon-057-3009c001-original-genuine-cano-1.jpg', 'https://www.absolutetoner.com/products/canon-057-black-original-genuine-oem-toner-cartridge-3009c001', 'Photo Canon 057 / 3009C001 original.'),
    'CANON728': ('canon-728-black-toner-cartridge-3500b002-1.png', 'https://tonerone.odoo.com/shop/genuine-canon-728-black-toner-cartridge-copy-8906', 'Photo Canon 728 noire originale.'),
    'CEXVV28N': ('c-exv28-canon-genuine-black-toner-cartri-1.jpg', 'https://www.cartridgesave.co.uk/2789b002aa.html', 'Photo Canon C-EXV28 noire; la référence source contient un V supplémentaire.'),
    'CEXV28C': ('canon-c-exv-28-cyan-genuine-toner-cartri-1.jpg', 'https://www.ebay.co.uk/b/Canon-Cyan-Toner-Cartridges/16204/bn_448439', 'Photo Canon C-EXV28 Cyan; visuel de gamme.'),
    'CEXV29N': ('canon-c-exv-29-toner-original-black-cart-1.jpg', 'https://www.ebay.co.uk/p/1604747833', 'Photo Canon C-EXV29 noire originale.'),
    'CEXV29C': ('canon-c-exv-29-cyan-toner-original-cartr-1.jpg', 'https://www.ebay.co.uk/p/1604747833', 'Photo Canon C-EXV29 Cyan Genuine.'),
    'CEXV33': ('c-exv33-canon-genuine-toner-cartridge-bl-1.webp', 'https://www.cartridgesave.co.uk/2785b002aa.html', 'Photo Canon C-EXV33 noire.'),
    'CEXV42': ('canon-c-exv-42-original-toner-cartridge--1.jpg', 'https://keneraint.com/canon-c-exv-42-genuine-toner', 'Photo Canon C-EXV42 Genuine.'),
    'CEXV54': ('canon-c-exv-54-black-toner-cartridge-gen-1.jpg', 'https://www.stech.ink/products/canon-toner-original-black-c-exv-54-irc-c3025-c3125-c3226i-1394c002ac', 'Photo Canon C-EXV54 noire originale.'),
    'CEXV60': ('canon-c-exv-60-genuine-original-toner-ca-1.jpg', 'https://atomoffice.com/products/canon-c-exv60-black-original-toner-cartridge', 'Photo Canon C-EXV60 noire originale.'),
    'CEXV54C': ('canon-c-exv-54-cyan-toner-cartridge-genu-1.jpg', 'https://www.amazon.sa/-/en/Canon-Toner-C-EXV-1395C002-St%C3%BCck/dp/B071K6DYX2', 'Photo Canon C-EXV54 Cyan / 1395C002.'),
}

# Prix de vente issus du catalogue ESS général (repères seulement, pas le prix client saisi).
benchmarks = {
    'HP85A': (38000, 'INF-009 — HP 85A / CE285A, correspondance exacte'),
    'HP26A': (75000, 'INF-008 — HP 26A / CF226A, correspondance exacte'),
    'HP203N': (52000, 'INF-006 — HP 203A noir / CF540A; famille proche, à confirmer'),
    'HP205N': (45000, 'INF-007 — HP 205A noir / CF530A; famille proche, à confirmer'),
}

# Anomalies ou remarques à garder visibles dans la base.
notes_by_ref = {
    'HP44A': 'Doublon source avec deux coûts : n°13 = 5 000 F; n°61 = 5 500 F. Les deux sont conservés; le premier est affiché en coût principal.',
    'HP131N': 'Référence répétée deux fois (n°39 et 45) au même prix; une seule fiche conservée.',
    'HP131C': 'Référence répétée deux fois (n°40 et 46) au même prix; une seule fiche conservée.',
    'HP36': 'La photo trouvée correspond à HP 36A / CB436A; le suffixe A est absent dans le PDF source.',
    'CEXVV28N': 'Code retranscrit tel qu’imprimé (« CEXVV28N »); visuel trouvé pour C-EXV28 noir. Confirmer le code exact.',
    'CANN047': 'Code retranscrit tel qu’imprimé (« CANN047 »); visuel trouvé pour Canon 047. Confirmer l’orthographe.',
    'CANON719': 'Visuel de la référence Canon 119 / 3479B001, souvent équivalente à 719 selon marché; confirmer la compatibilité exacte.',
    'CANON045N': 'Visuel disponible de la gamme Canon 045 en boîte multicolore; l’image ne montre pas la cartouche noire seule.',
    'CANON069C': 'Aucune photo OEM couleur fiable trouvée; à compléter avec une photo fournisseur ou constructeur.',
    'CANON052': 'Aucune photo OEM suffisamment vérifiable trouvée; à compléter.',
    'HP117N': 'Photo correspond à HP 117A / W2070A; variante couleur déduite du code source N.',
}

# Prix de la liste d'achat non renseignés dans la source et exclus de la base principale selon votre choix.
excluded_missing = ['CEXV42GIGA', 'CEXV33GIGA', 'CEXV65GIGA', 'CEXV64', 'CEXV59', 'CEXV59GIGA', 'CEXV37', 'CEXV34', 'GR15', 'GPR18']

# Dédoublonnage par référence, en conservant les lignes source et les divergences de prix.
by_ref = OrderedDict()
for num, ref, price in raw:
    page = 1 if num <= 46 else (2 if num <= 96 else 3)
    if price is None:
        continue
    if ref not in by_ref:
        by_ref[ref] = {'ref': ref, 'price': price, 'price2': None, 'rows': [], 'page': page, 'conflict': False}
    rec = by_ref[ref]
    rec['rows'].append((num, page, price))
    if price != rec['price']:
        rec['conflict'] = True
        if rec['price2'] is None:
            rec['price2'] = price
products = list(by_ref.values())
assert len(products) == 87, f'Attendu 87 références uniques tarifées, trouvé {len(products)}'

# Types et couleurs (N/C sont interprétés comme noir/couleur, à valider avec les codes fabricant).
def brand_for(ref: str) -> str:
    if ref.startswith('HP'):
        return 'HP'
    if ref.startswith(('CANON', 'CANN')):
        return 'Canon'
    if ref.startswith(('CEXV', 'CEXVV', 'GPR', 'GR')):
        return 'Canon / copieur (à confirmer)'
    if ref.startswith('TAMB'):
        return 'À confirmer (tambour)'
    return 'À confirmer'

def kind_for(ref: str) -> str:
    if ref.startswith('TAMB'):
        return 'Tambour / unité d’image'
    if ref.startswith(('CEXV', 'CEXVV', 'GPR', 'GR')):
        return 'Toner photocopieur'
    return 'Cartouche / toner imprimante'

def color_for(ref: str) -> str:
    if ref.startswith('TAMB'):
        return 'Tambour'
    if ref.endswith('N'):
        return 'Noir (suffixe N à confirmer)'
    if ref.endswith('C'):
        return 'Cyan/couleur (suffixe C à confirmer)'
    return 'Non précisée dans la source'

def description_for(ref: str) -> str:
    kind = kind_for(ref)
    color = color_for(ref)
    if ref.startswith('TAMB'):
        return f'Tambour / unité d’image — {ref}'
    if color.startswith('Noir'):
        color_short = 'noir'
    elif color.startswith('Cyan'):
        color_short = 'cyan / couleur'
    else:
        color_short = 'couleur à préciser'
    if ref.startswith(('CEXV', 'CEXVV')):
        return f'Toner photocopieur Canon — {ref} ({color_short})'
    if ref.startswith(('CANON', 'CANN')):
        return f'Cartouche/toner Canon — {ref} ({color_short})'
    return f'Cartouche/toner HP — {ref} ({color_short})'

def source_text(rec: dict) -> str:
    return '; '.join(f'n°{n} p.{p}' for n, p, _ in rec['rows'])

def photo_status(ref: str, item: dict | None) -> str:
    if item is None:
        return 'Photo à ajouter'
    if ref in ('HP36', 'CEXVV28N', 'CANN047', 'CANON719', 'CANON045N', 'TAMB19A', 'TAMB120A'):
        return 'Visuel de famille / équivalence — à vérifier'
    if ref.endswith(('N', 'C')) and (ref.startswith('HP') or ref.startswith('CANON') or ref.startswith('CANN')):
        return 'Visuel OEM de gamme/couleur — suffixe source à confirmer'
    if ref.startswith('CEXV'):
        return 'Photo de la gamme Canon C-EXV'
    return 'Photo Web du modèle / gamme'

# Mise en page & couleurs.
NAVY = '15324F'
BLUE = '1F4E78'
ORANGE = 'F28C28'
PALE_BLUE = 'EAF2F8'
PALE_YELLOW = 'FFF2CC'
PALE_RED = 'FCE4D6'
PALE_GREEN = 'E2F0D9'
LIGHT = 'F5F8FB'
MID = 'D9E2F3'
DARK = '1E293B'
WHITE = 'FFFFFF'
GRAY = '666666'
THIN_GRAY = Side(style='thin', color='D7E0E8')

wb = Workbook()
wb.remove(wb.active)
wb.properties.title = 'Base de données cartouches et toners — E.S.S. 2026'
wb.properties.subject = 'Suivi des coûts, prix de vente, visuels, ventes et réceptions'
wb.properties.creator = 'Arena.ai'
wb.properties.description = 'Transcription des catalogues PDF fournis par l’utilisateur. Prix client à saisir manuellement.'
try:
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = 'auto'
except Exception:
    pass

# Helpers de style.
def title_block(ws, title, subtitle, last_col):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    c = ws.cell(1, 1, title)
    c.fill = PatternFill('solid', fgColor=NAVY)
    c.font = Font(name='Aptos Display', size=19, bold=True, color=WHITE)
    c.alignment = Alignment(vertical='center')
    ws.row_dimensions[1].height = 36
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    c2 = ws.cell(2, 1, subtitle)
    c2.fill = PatternFill('solid', fgColor='EAF1F8')
    c2.font = Font(name='Aptos', size=10, italic=True, color=BLUE)
    c2.alignment = Alignment(vertical='center', wrap_text=True)
    ws.row_dimensions[2].height = 30

def header_row(ws, row, headers):
    for col, text in enumerate(headers, 1):
        c = ws.cell(row, col, text)
        c.fill = PatternFill('solid', fgColor=BLUE)
        c.font = Font(name='Aptos', size=10, bold=True, color=WHITE)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = Border(bottom=Side(style='medium', color=ORANGE))
    ws.row_dimensions[row].height = 40

def apply_base(ws):
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.5
    ws.sheet_view.zoomScale = 90

def add_table(ws, ref, name, style='TableStyleMedium2'):
    t = Table(displayName=name, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name=style, showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
    ws.add_table(t)

def set_currency(cell):
    cell.number_format = '#,##0 "F";[Red]-#,##0 "F";–'

def set_percent(cell):
    cell.number_format = '0.0%'

def add_thumb(src: Path, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with PILImage.open(src) as im:
        im = im.convert('RGBA')
        im.thumbnail((118, 72), PILImage.Resampling.LANCZOS)
        canvas = PILImage.new('RGBA', (124, 78), (255, 255, 255, 255))
        canvas.alpha_composite(im, ((124 - im.width) // 2, (78 - im.height) // 2))
        canvas.convert('RGB').save(out, 'JPEG', quality=84, optimize=True)
    return out

# Feuille 1 : catalogue opérationnel filtrable.
ws = wb.create_sheet('Base produits')
apply_base(ws)
title_block(ws, 'E.S.S. — Base produits cartouches & toners', 'Coûts issus de « Prix imprimante.pdf » · FCFA HT confirmés · prix de vente client à renseigner manuellement · filtrer avec les flèches des en-têtes.', 20)
headers = [
    'Fiche visuelle', 'Référence (source)', 'Marque', 'Famille', 'Couleur / variante', 'Désignation',
    'Nature déclarée', 'Prix achat HT', 'Autre prix achat repéré', 'Prix vente client HT — à saisir',
    'Repère tarif ESS HT', 'Source du repère ESS', 'Marge brute HT', 'Marge % sur vente',
    'Stock initial', 'Entrées', 'Sorties', 'Stock théorique', 'Contrôle / note', 'Source achat',
]
header_row(ws, 4, headers)
first_data_row = 5
last_data_row = first_data_row + len(products) - 1
for idx, rec in enumerate(products):
    r = first_data_row + idx
    ref = rec['ref']
    img_item = photo_map.get(ref)
    # Liens et champs descriptifs.
    a = ws.cell(r, 1, 'Ouvrir photo')
    visual_row = first_data_row + idx
    a.hyperlink = f"#'Catalogue visuel'!A{visual_row}"
    a.style = 'Hyperlink'
    a.alignment = Alignment(horizontal='center', vertical='center')
    values = [
        None, ref, brand_for(ref), kind_for(ref), color_for(ref), description_for(ref),
        'Original (selon votre confirmation)', rec['price'], rec['price2'], None,
        benchmarks.get(ref, (None, None))[0], benchmarks.get(ref, (None, None))[1],
        f'=IF(OR(J{r}="",H{r}=""),"",J{r}-H{r})',
        f'=IF(OR(J{r}="",H{r}="",J{r}=0),"",M{r}/J{r})',
        None,
        f"=SUMIF('Réceptions'!$C$5:$C$504,$B{r},'Réceptions'!$E$5:$E$504)",
        f"=SUMIF('Ventes'!$D$5:$D$504,$B{r},'Ventes'!$F$5:$F$504)",
        f'=IF(O{r}="","",O{r}+P{r}-Q{r})',
        None,
        source_text(rec),
    ]
    for col, value in enumerate(values, 1):
        if col == 1:
            continue
        c = ws.cell(r, col, value)
        c.alignment = Alignment(vertical='center', wrap_text=(col in (4, 5, 6, 12, 19, 20)))
        c.border = Border(bottom=THIN_GRAY)
    # Notes de contrôle.
    issues = []
    if ref in notes_by_ref:
        issues.append(notes_by_ref[ref])
    if ref in benchmarks and rec['price'] and benchmarks[ref][0] and benchmarks[ref][0] / rec['price'] >= 5:
        issues.append('Écart très marqué entre coût d’achat et tarif de vente catalogue ESS; confirmer SKU et authenticité avant de publier un prix « original ».')
    if img_item is None:
        issues.append('Photo exacte non trouvée; visuel à ajouter.')
    if not issues:
        issues.append('Prix de vente et stock initial à compléter.')
    ws.cell(r, 19, ' '.join(issues))
    # Couleurs des cellules de saisie vs calcul.
    for col in (10, 15):
        ws.cell(r, col).fill = PatternFill('solid', fgColor=PALE_YELLOW)
    for col in (13, 14, 16, 17, 18):
        ws.cell(r, col).fill = PatternFill('solid', fgColor=PALE_BLUE)
    if rec['conflict']:
        ws.cell(r, 8).fill = PatternFill('solid', fgColor=PALE_RED)
        ws.cell(r, 9).fill = PatternFill('solid', fgColor=PALE_RED)
    elif rec['price2'] is not None:
        ws.cell(r, 9).fill = PatternFill('solid', fgColor=PALE_RED)
    if ref in benchmarks:
        ws.cell(r, 11).fill = PatternFill('solid', fgColor='E2F0D9')
    if issues and ('confirmer' in ' '.join(issues).lower() or 'vérifier' in ' '.join(issues).lower()):
        ws.cell(r, 19).fill = PatternFill('solid', fgColor='FCE4D6')
    for col in (8, 9, 10, 11, 13):
        set_currency(ws.cell(r, col))
    set_percent(ws.cell(r, 14))
    ws.cell(r, 8).comment = Comment('Prix unitaire retranscrit du PDF fournisseur. La devise/les taxes de cette feuille ont été confirmées par l’utilisateur comme FCFA HT.', 'Arena.ai')
    ws.cell(r, 10).comment = Comment('Champ laissé vide conformément à votre choix de saisir les tarifs client manuellement. Les repères du catalogue ESS sont dans la colonne précédente et dans l’onglet Tarifs ESS.', 'Arena.ai')
    ws.cell(r, 15).comment = Comment('Saisir le stock constaté au démarrage; le stock théorique sera ensuite calculé avec les réceptions et les ventes.', 'Arena.ai')
    for col in range(1, 21):
        ws.cell(r, col).font = Font(name='Aptos', size=9, color=DARK, bold=(col == 2))
    ws.row_dimensions[r].height = 34

# Largeurs & formats de la base.
widths = {'A': 15, 'B': 18, 'C': 22, 'D': 25, 'E': 30, 'F': 43, 'G': 27, 'H': 17, 'I': 20, 'J': 23, 'K': 19, 'L': 42, 'M': 17, 'N': 18, 'O': 15, 'P': 14, 'Q': 14, 'R': 17, 'S': 66, 'T': 22}
for col, width in widths.items():
    ws.column_dimensions[col].width = width
ws.freeze_panes = 'G5'
ws.auto_filter.ref = f'A4:T{last_data_row}'
add_table(ws, f'A4:T{last_data_row}', 'BaseProduits', 'TableStyleMedium2')
ws.sheet_view.zoomScale = 75
ws.page_setup.orientation = 'landscape'
ws.page_setup.paperSize = ws.PAPERSIZE_A3

# Feuille 2 : catalogue visuel statique, afin que les miniatures restent alignées pendant le tri de la base.
vis = wb.create_sheet('Catalogue visuel')
apply_base(vis)
title_block(vis, 'Catalogue visuel — cartouches & toners', 'Visuels indicatifs trouvés en ligne; les liens de source sont fournis. Une photo en ligne n’atteste pas que le stock réel est original ou identique.', 8)
vis_headers = ['Référence', 'Photo', 'Désignation', 'Prix achat HT', 'Repère ESS HT', 'Prix vente client HT', 'Statut / note visuel', 'Source image Web']
header_row(vis, 4, vis_headers)
vis.column_dimensions['A'].width = 18
vis.column_dimensions['B'].width = 19
vis.column_dimensions['C'].width = 48
vis.column_dimensions['D'].width = 18
vis.column_dimensions['E'].width = 18
vis.column_dimensions['F'].width = 23
vis.column_dimensions['G'].width = 56
vis.column_dimensions['H'].width = 23
vis.freeze_panes = 'A5'

for idx, rec in enumerate(products):
    r = first_data_row + idx
    ref = rec['ref']
    item = photo_map.get(ref)
    vals = [ref, None, description_for(ref), rec['price'], benchmarks.get(ref, (None, None))[0], None, photo_status(ref, item), None]
    for col, val in enumerate(vals, 1):
        if col == 2 or col == 8:
            continue
        c = vis.cell(r, col, val)
        c.alignment = Alignment(vertical='center', wrap_text=col in (3, 7))
        c.border = Border(bottom=THIN_GRAY)
        c.font = Font(name='Aptos', size=9, color=DARK, bold=(col == 1))
    set_currency(vis.cell(r, 4))
    set_currency(vis.cell(r, 5))
    vis.cell(r, 6, None)
    vis.cell(r, 6).fill = PatternFill('solid', fgColor=PALE_YELLOW)
    vis.cell(r, 6).comment = Comment('Saisie manuelle; le prix client n’est pas calculé automatiquement.', 'Arena.ai')
    if item:
        src_file, url, note = item
        src_path = IMG_DIR / src_file
        # Le nom du fichier peut varier dans l'extension seulement si l'image_search a servi une autre variante.
        if src_path.exists():
            thumb_path = add_thumb(src_path, THUMBS / f'{ref.replace("/", "_")}.jpg')
            img = XLImage(str(thumb_path))
            img.width, img.height = 116, 73
            img.anchor = f'B{r}'
            vis.add_image(img)
            vis.cell(r, 7, photo_status(ref, item) + ' — ' + note)
            linkcell = vis.cell(r, 8, 'Ouvrir la source')
            linkcell.hyperlink = url
            linkcell.style = 'Hyperlink'
            linkcell.alignment = Alignment(vertical='center', horizontal='center')
        else:
            vis.cell(r, 2, 'Fichier visuel introuvable')
            vis.cell(r, 2).fill = PatternFill('solid', fgColor=PALE_RED)
            vis.cell(r, 7, 'Photo à ajouter')
    else:
        vis.cell(r, 2, 'Photo exacte à ajouter')
        vis.cell(r, 2).fill = PatternFill('solid', fgColor=PALE_YELLOW)
        vis.cell(r, 2).font = Font(name='Aptos', size=9, color=GRAY, italic=True)
        vis.cell(r, 7, 'Photo à ajouter — aucune image OEM assez fiable trouvée.')
        vis.cell(r, 7).fill = PatternFill('solid', fgColor=PALE_YELLOW)
    vis.row_dimensions[r].height = 60

# Pas de tri automatique sur cette feuille : les images restent alignées sur leur référence.
vis.page_setup.orientation = 'landscape'
vis.page_setup.paperSize = vis.PAPERSIZE_A3
vis.sheet_view.zoomScale = 85

# Feuille 3 : saisie des ventes.
ventas = wb.create_sheet('Ventes')
apply_base(ventas)
title_block(ventas, 'Journal des ventes', 'Choisir une référence; la désignation et le prix client se reprennent de « Base produits ». Renseigner d’abord le prix client sur cette base.', 12)
vent_headers = ['Date', 'N° facture', 'Client', 'Référence', 'Désignation', 'Qté', 'Prix vente unitaire HT', 'Remise %', 'Total ligne HT', 'Marge brute estimée HT', 'Mode de paiement', 'Note']
header_row(ventas, 4, vent_headers)
for col, width in {'A': 15, 'B': 18, 'C': 26, 'D': 18, 'E': 43, 'F': 10, 'G': 22, 'H': 13, 'I': 20, 'J': 23, 'K': 20, 'L': 36}.items():
    ventas.column_dimensions[col].width = width
for r in range(5, 505):
    ventas.cell(r, 5, f'''=IF($D{r}="","",IFERROR(VLOOKUP($D{r},'Base produits'!$B${first_data_row}:$F${last_data_row},5,FALSE),""))''')
    ventas.cell(r, 7, f'''=IF($D{r}="","",IFERROR(IF(VLOOKUP($D{r},'Base produits'!$B${first_data_row}:$J${last_data_row},9,FALSE)="","",VLOOKUP($D{r},'Base produits'!$B${first_data_row}:$J${last_data_row},9,FALSE)),""))''')
    ventas.cell(r, 9, f'=IF(OR($D{r}="",$F{r}="",$G{r}=""),"",$F{r}*$G{r}*(1-IFERROR($H{r},0)))')
    ventas.cell(r, 10, f'''=IF(OR($D{r}="",$F{r}="",$G{r}=""),"",($G{r}-IFERROR(VLOOKUP($D{r},'Base produits'!$B${first_data_row}:$H${last_data_row},7,FALSE),0))*$F{r}*(1-IFERROR($H{r},0)))''')
    for col in range(1, 13):
        c = ventas.cell(r, col)
        c.font = Font(name='Aptos', size=9, color=DARK)
        c.alignment = Alignment(vertical='center', wrap_text=col in (3, 5, 12))
        c.border = Border(bottom=THIN_GRAY)
    for col in (1, 2, 3, 4, 6, 8, 11, 12):
        ventas.cell(r, col).fill = PatternFill('solid', fgColor=PALE_YELLOW)
    for col in (5, 7, 9, 10):
        ventas.cell(r, col).fill = PatternFill('solid', fgColor=PALE_BLUE)
    ventas.cell(r, 1).number_format = 'dd/mm/yyyy'
    for col in (7, 9, 10):
        set_currency(ventas.cell(r, col))
    set_percent(ventas.cell(r, 8))
    ventas.row_dimensions[r].height = 23
ventas.freeze_panes = 'A5'
add_table(ventas, 'A4:L504', 'JournalVentes', 'TableStyleMedium4')
ventas.sheet_view.zoomScale = 85
ventas.page_setup.orientation = 'landscape'
ventas.page_setup.paperSize = ventas.PAPERSIZE_A3

# Feuille 4 : réceptions/achats pour calculer les entrées de stock.
rec_ws = wb.create_sheet('Réceptions')
apply_base(rec_ws)
title_block(rec_ws, 'Réceptions et entrées de stock', 'Saisir une ligne par réception fournisseur. Le coût unitaire est prérempli depuis la base; corriger la valeur si la facture fournisseur diffère.', 8)
recv_headers = ['Date', 'Fournisseur', 'Référence', 'Désignation', 'Qté reçue', 'Prix achat unitaire HT', 'Total achat HT', 'Facture / note']
header_row(rec_ws, 4, recv_headers)
for col, width in {'A': 15, 'B': 26, 'C': 18, 'D': 43, 'E': 13, 'F': 23, 'G': 20, 'H': 34}.items():
    rec_ws.column_dimensions[col].width = width
for r in range(5, 505):
    rec_ws.cell(r, 4, f'''=IF($C{r}="","",IFERROR(VLOOKUP($C{r},'Base produits'!$B${first_data_row}:$F${last_data_row},5,FALSE),""))''')
    rec_ws.cell(r, 6, f'''=IF($C{r}="","",IFERROR(IF(VLOOKUP($C{r},'Base produits'!$B${first_data_row}:$H${last_data_row},7,FALSE)="","",VLOOKUP($C{r},'Base produits'!$B${first_data_row}:$H${last_data_row},7,FALSE)),""))''')
    rec_ws.cell(r, 7, f'=IF(OR($C{r}="",$E{r}="",$F{r}=""),"",$E{r}*$F{r})')
    for col in range(1, 9):
        c = rec_ws.cell(r, col)
        c.font = Font(name='Aptos', size=9, color=DARK)
        c.alignment = Alignment(vertical='center', wrap_text=col in (2, 4, 8))
        c.border = Border(bottom=THIN_GRAY)
    for col in (1, 2, 3, 5, 6, 8):
        rec_ws.cell(r, col).fill = PatternFill('solid', fgColor=PALE_YELLOW)
    for col in (4, 7):
        rec_ws.cell(r, col).fill = PatternFill('solid', fgColor=PALE_BLUE)
    rec_ws.cell(r, 1).number_format = 'dd/mm/yyyy'
    set_currency(rec_ws.cell(r, 6))
    set_currency(rec_ws.cell(r, 7))
rec_ws.freeze_panes = 'A5'
add_table(rec_ws, 'A4:H504', 'JournalReceptions', 'TableStyleMedium4')
rec_ws.sheet_view.zoomScale = 90
rec_ws.page_setup.orientation = 'landscape'
rec_ws.page_setup.paperSize = rec_ws.PAPERSIZE_A3

# Validations.
try:
    wb.defined_names.add(DefinedName('ListeReferences', attr_text=f"'Base produits'!$B${first_data_row}:$B${last_data_row}"))
except Exception:
    wb.defined_names['ListeReferences'] = DefinedName('ListeReferences', attr_text=f"'Base produits'!$B${first_data_row}:$B${last_data_row}")
for sheet, target in ((ventas, 'D5:D504'), (rec_ws, 'C5:C504')):
    dv = DataValidation(type='list', formula1='=ListeReferences', allow_blank=True)
    dv.error = 'Choisissez une référence de la base produits.'
    dv.errorTitle = 'Référence non reconnue'
    dv.prompt = 'Sélectionner une référence déjà créée dans Base produits.'
    dv.promptTitle = 'Choisir une référence'
    sheet.add_data_validation(dv)
    dv.add(target)

# Feuille 5 : repères du catalogue général (page 12).
cat = wb.create_sheet('Tarifs ESS')
apply_base(cat)
title_block(cat, 'Repères de vente du catalogue ESS 2026', 'Prix du catalogue général, page 12 — indicatifs et HT. Ils sont séparés des prix client saisis dans la base afin d’éviter toute association automatique incertaine.', 7)
cat_headers = ['Réf. catalogue', 'Désignation', 'Type indiqué', 'Conditionnement', 'Prix catalogue HT', 'Utilisation', 'Source']
header_row(cat, 4, cat_headers)
cat_rows = [
    ('INF-006', 'Toner laser noir original — HP 203A (CF540A)', 'Original', 'Unité', 52000, 'Repère pour HP203N noir; famille proche, confirmer la correspondance.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-007', 'Toner laser noir original — HP 205A (CF530A)', 'Original', 'Unité', 45000, 'Repère pour HP205N noir; famille proche, confirmer la correspondance.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-008', 'Toner laser noir original — HP 26A (CF226A)', 'Original', 'Unité', 75000, 'Repère HP26A; correspondance exacte de gamme.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-009', 'Toner laser noir original — HP 85A (CE285A)', 'Original', 'Unité', 38000, 'Repère HP85A; correspondance exacte de gamme.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-010', 'Toner laser noir original — HP 84A (CF284A)', 'Original', 'Unité', 95000, 'Article du catalogue; aucune référence d’achat identique dans la liste source.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-011', 'Cartouche d’encre noire compatible (HP / Canon)', 'Compatible', 'Unité', 8000, 'Tarif générique, non associé à une référence précise.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-012', 'Cartouche d’encre couleur compatible (HP / Canon)', 'Compatible', 'Unité', 10000, 'Tarif générique, non associé à une référence précise.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-013', 'Toner laser noir compatible (Brother / Samsung / HP)', 'Compatible', 'Unité', 15000, 'Tarif générique, non associé à une référence précise.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-014', 'Cartouche photocopieur RICOH MP C3003 / 3503', 'À préciser', 'Unité', None, 'Sur devis.', 'ESS_Catalogue_General_2026.pdf, p.12'),
    ('INF-015', 'Kit de maintenance / tambour', 'À préciser', 'Unité', None, 'Sur devis.', 'ESS_Catalogue_General_2026.pdf, p.12'),
]
for i, row in enumerate(cat_rows, 5):
    for j, val in enumerate(row, 1):
        c = cat.cell(i, j, val)
        c.font = Font(name='Aptos', size=9, color=DARK)
        c.alignment = Alignment(vertical='center', wrap_text=True)
        c.border = Border(bottom=THIN_GRAY)
    if row[4] is not None:
        set_currency(cat.cell(i, 5))
    cat.row_dimensions[i].height = 36
for col, width in {'A': 18, 'B': 52, 'C': 18, 'D': 16, 'E': 20, 'F': 58, 'G': 42}.items():
    cat.column_dimensions[col].width = width
cat.freeze_panes = 'A5'
add_table(cat, f'A4:G{4 + len(cat_rows)}', 'TarifsCatalogue', 'TableStyleMedium2')
cat.page_setup.orientation = 'landscape'

# Feuille 6 : tableau de bord.
dash = wb.create_sheet('Tableau de bord', 0)
apply_base(dash)
title_block(dash, 'E.S.S. — Suivi commercial des cartouches & toners', 'Base de travail créée à partir des deux PDF fournis · génération du 04/10/2026 · montants confirmés FCFA HT.', 8)
dash.column_dimensions['A'].width = 4
dash.column_dimensions['B'].width = 34
dash.column_dimensions['C'].width = 22
dash.column_dimensions['D'].width = 5
dash.column_dimensions['E'].width = 36
dash.column_dimensions['F'].width = 25
dash.column_dimensions['G'].width = 5
dash.column_dimensions['H'].width = 25

def metric(label, formula, row, col=2, number_format=None, static_value=None):
    dash.cell(row, col, label)
    dash.cell(row, col).font = Font(name='Aptos', size=10, bold=True, color=WHITE)
    dash.cell(row, col).fill = PatternFill('solid', fgColor=BLUE)
    dash.cell(row, col).alignment = Alignment(vertical='center', wrap_text=True)
    value = static_value if static_value is not None else formula
    c = dash.cell(row, col + 1, value)
    c.font = Font(name='Aptos Display', size=17, bold=True, color=NAVY)
    c.fill = PatternFill('solid', fgColor=PALE_BLUE)
    c.alignment = Alignment(horizontal='center', vertical='center')
    if number_format:
        c.number_format = number_format
    dash.row_dimensions[row].height = 34

metric('Références actives (uniques)', f"=COUNTA('Base produits'!$B${first_data_row}:$B${last_data_row})", 5)
metric('Références avec achat renseigné', f"=COUNT('Base produits'!$H${first_data_row}:$H${last_data_row})", 6)
metric('Prix vente client à saisir', f"=COUNTBLANK('Base produits'!$J${first_data_row}:$J${last_data_row})", 7)
metric('Ventes HT enregistrées', '=SUM(Ventes!$I$5:$I$504)', 8, number_format='#,##0 "F";[Red]-#,##0 "F";–')
metric('Marge brute estimée HT', '=SUM(Ventes!$J$5:$J$504)', 9, number_format='#,##0 "F";[Red]-#,##0 "F";–')
metric('Références exclues (prix d’achat manquant)', '', 10, static_value=len(excluded_missing))
photo_exact_count = sum(1 for p in products if p['ref'] in photo_map)
metric('Visuels trouvés (indicatifs)', f'''=COUNTIF('Catalogue visuel'!$H${first_data_row}:$H${last_data_row},"Ouvrir la source")''', 11)
metric('Visuels à ajouter', f"=COUNTBLANK('Catalogue visuel'!$H${first_data_row}:$H${last_data_row})", 12)

# Alertes qualitatives.
dash.merge_cells('E5:H5')
dash['E5'] = 'À vérifier avant utilisation commerciale'
dash['E5'].fill = PatternFill('solid', fgColor=ORANGE)
dash['E5'].font = Font(name='Aptos', size=12, bold=True, color=WHITE)
dash['E5'].alignment = Alignment(vertical='center')
alerts = [
    'Type déclaré : original (selon votre réponse). Toutefois, certains coûts d’achat sont très inférieurs aux prix de vente d’origine du catalogue ESS (ex. HP85A : 3 500 F vs 38 000 F; HP26A : 8 000 F vs 75 000 F). Vérifier SKU, conditionnement et authenticité avant de vendre comme original.',
    'HP44A figure deux fois : 5 000 F et 5 500 F. Le premier tarif est affiché en prix principal; le second est conservé à côté. À confirmer.',
    'La source ne donne aucun prix d’achat pour les références 93 à 102; elles ont été exclues de la base principale conformément à votre choix.',
    'Plusieurs suffixes N/C et codes proches ont été interprétés comme noir/cyan pour faciliter le repérage; confirmer les codes fabricant sur les boîtes.',
    'Les photos sont des images Web indicatives, pas une preuve que le produit en stock est identique ou authentique. Les sources sont cliquables dans l’onglet Catalogue visuel.',
]
for i, text in enumerate(alerts, 6):
    dash.merge_cells(start_row=i, start_column=5, end_row=i, end_column=8)
    c = dash.cell(i, 5, '• ' + text)
    c.fill = PatternFill('solid', fgColor='FFF8E8' if i != 6 else PALE_RED)
    c.font = Font(name='Aptos', size=9, color=DARK)
    c.alignment = Alignment(vertical='center', wrap_text=True)
    dash.row_dimensions[i].height = 52 if i in (6, 10) else 40

# Instructions rapides.
dash.merge_cells('B15:H15')
dash['B15'] = 'Démarrage rapide'
dash['B15'].fill = PatternFill('solid', fgColor=BLUE)
dash['B15'].font = Font(name='Aptos', size=12, bold=True, color=WHITE)
steps = [
    ('1', 'Dans « Base produits », saisissez vos prix client dans les cellules jaunes; le champ est laissé vide exprès, selon votre choix de fixation manuelle.'),
    ('2', 'Saisissez le stock constaté au départ dans « Stock initial ». Le stock théorique se calcule ensuite à partir des réceptions et des ventes.'),
    ('3', 'Enregistrez les achats/réceptions dans « Réceptions » et les opérations clients dans « Ventes ». Les références sont disponibles dans les listes déroulantes.'),
    ('4', 'Utilisez « Catalogue visuel » pour consulter les photos; les cellules jaunes signalent les références pour lesquelles une photo fiable reste à ajouter.'),
]
for row, (n, text) in enumerate(steps, 16):
    dash.cell(row, 2, n)
    dash.cell(row, 2).fill = PatternFill('solid', fgColor=ORANGE)
    dash.cell(row, 2).font = Font(name='Aptos', size=12, bold=True, color=WHITE)
    dash.cell(row, 2).alignment = Alignment(horizontal='center', vertical='center')
    dash.merge_cells(start_row=row, start_column=3, end_row=row, end_column=8)
    dash.cell(row, 3, text)
    dash.cell(row, 3).font = Font(name='Aptos', size=9, color=DARK)
    dash.cell(row, 3).alignment = Alignment(vertical='center', wrap_text=True)
    dash.cell(row, 3).fill = PatternFill('solid', fgColor=LIGHT)
    dash.row_dimensions[row].height = 36
dash_last = 21
dash.merge_cells(start_row=dash_last, start_column=2, end_row=dash_last, end_column=8)
dash.cell(dash_last, 2, 'Onglets : Base produits (filtrable) · Catalogue visuel · Ventes · Réceptions · Tarifs ESS · Guide & contrôles.')
dash.cell(dash_last, 2).font = Font(name='Aptos', size=9, italic=True, color=GRAY)
dash.cell(dash_last, 2).alignment = Alignment(wrap_text=True, vertical='center')
dash.row_dimensions[dash_last].height = 26
dash.freeze_panes = 'B5'

# Feuille 7 : guide et audit de la transcription.
guide = wb.create_sheet('Guide')
apply_base(guide)
title_block(guide, 'Guide d’utilisation & contrôles de source', 'Ce classeur est une base de gestion, à compléter avec vos coûts confirmés, prix clients, photos réelles et stocks de départ.', 6)
for col, width in {'A': 5, 'B': 32, 'C': 42, 'D': 42, 'E': 42, 'F': 34}.items():
    guide.column_dimensions[col].width = width
sections = [
    ('Périmètre', 'Cartouches/toners et tambours tarifés dans « Prix imprimante.pdf ». 100 lignes tarifaires étaient présentes; 10 lignes sans prix d’achat ont été écartées et les doublons ont été regroupés, soit 87 références uniques avec prix.'),
    ('Prix d’achat', 'Les montants de la source ont été retranscrits comme coûts d’achat unitaires. Vous avez confirmé FCFA HT. HP44A garde 5 000 F en tarif principal et 5 500 F dans « Autre prix achat repéré »; choisissez le tarif réel selon le fournisseur.'),
    ('Prix de vente', 'Vous avez demandé une fixation manuelle. La colonne « Prix vente client HT » reste donc vide (cellules jaunes). Les repères ESS 2026 sont séparés dans une colonne et dans l’onglet « Tarifs ESS »; ils ne sont pas injectés automatiquement.'),
    ('Repères catalogue', 'Le catalogue général page 12 affiche 5 tarifs de toners HP originaux et plusieurs prix génériques compatibles. Seuls les repères HP85A et HP26A sont mis comme correspondances exactes; HP203N/HP205N sont des correspondances de gamme à confirmer.'),
    ('Type original / compatible', 'Vous avez indiqué que les références sont originales. Attention : certains prix d’achat (notamment HP85A, HP26A, HP203N et HP205N) sont très éloignés des tarifs catalogue des toners originaux. Vérifier les emballages, références fabricant et factures avant de publier ces articles comme originaux.'),
    ('Photos', 'Les visuels viennent de pages Web liées dans « Catalogue visuel ». Ils sont fournis pour faciliter l’identification, pas comme preuve de la nature du stock réel. Les références sans image OEM suffisamment fiable sont marquées « Photo à ajouter ».'),
    ('Codes à contrôler', '« CEXVV28N » et « CANN047 » sont conservés tels qu’imprimés, avec une note sur leur probable orthographe. « HP36 » apparaît sans suffixe A dans le prix d’achat, alors que le visuel trouvé correspond à HP36A. Le numérotage source saute les n°53 et 54.'),
    ('Doublons', 'HP44A apparaît avec deux coûts (5 000 F au n°13 et 5 500 F au n°61). HP131N et HP131C sont répétés deux fois au même tarif; une seule fiche par référence est conservée.'),
    ('Références écartées (prix absent)', ', '.join(excluded_missing) + '. Elles ne figurent pas dans la base principale; ajoutez-les uniquement après confirmation des prix d’achat.'),
    ('Stocks', 'Entrez une valeur de départ dans « Stock initial ». Chaque réception ajoutée dans l’onglet « Réceptions » augmente le stock; chaque vente saisie dans « Ventes » le réduit. Sans stock initial, le stock théorique reste vide pour éviter d’afficher un faux zéro.'),
    ('Conditions catalogue', 'Le catalogue ESS précise que les prix 2026 sont indicatifs, hors taxes, communiqués sur devis et susceptibles de remises. Les tarifs d’origine s’appliquent uniquement à la référence et à la version correspondantes.'),
]
row = 4
for title, body in sections:
    guide.merge_cells(start_row=row, start_column=2, end_row=row, end_column=2)
    guide.cell(row, 2, title)
    guide.cell(row, 2).fill = PatternFill('solid', fgColor=BLUE)
    guide.cell(row, 2).font = Font(name='Aptos', size=10, bold=True, color=WHITE)
    guide.cell(row, 2).alignment = Alignment(vertical='center', wrap_text=True)
    guide.merge_cells(start_row=row, start_column=3, end_row=row, end_column=6)
    guide.cell(row, 3, body)
    guide.cell(row, 3).font = Font(name='Aptos', size=9, color=DARK)
    guide.cell(row, 3).alignment = Alignment(vertical='center', wrap_text=True)
    guide.cell(row, 3).fill = PatternFill('solid', fgColor='FFF8E8' if title in ('Type original / compatible', 'Doublons', 'Codes à contrôler') else LIGHT)
    guide.row_dimensions[row].height = 52 if len(body) < 260 else 68
    row += 1
guide.freeze_panes = 'B4'
guide.page_setup.orientation = 'landscape'
guide.page_setup.paperSize = guide.PAPERSIZE_A3

# Re-index names / formulas and subtle formatting.
for sheet in wb.worksheets:
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.sheet_format.defaultRowHeight = 20
    sheet.print_title_rows = '1:4'
    sheet.sheet_view.showGridLines = False

# Page color & tab order styles.
for s in wb.worksheets:
    if s.title in ('Tableau de bord',):
        s.sheet_properties.tabColor = ORANGE
    elif s.title in ('Base produits', 'Ventes', 'Réceptions'):
        s.sheet_properties.tabColor = BLUE
    elif s.title == 'Catalogue visuel':
        s.sheet_properties.tabColor = '70AD47'
    else:
        s.sheet_properties.tabColor = 'A6A6A6'

# Force formulas to recalculate when opened in Excel/LibreOffice.
try:
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = 'auto'
except Exception:
    pass

wb.save(OUT)
print(f'Créé : {OUT}')
print(f'Lignes source : {len(raw)} | références tarifées uniques : {len(products)} | sans prix exclues : {len(excluded_missing)} | visuels map : {len(photo_map)}')
print(f'Photos effectivement intégrées : {photo_exact_count}')
