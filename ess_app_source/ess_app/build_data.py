from pathlib import Path
import ast, json, re, shutil
from PIL import Image as PILImage

ROOT = Path('/home/user')
APP = ROOT / 'ess_app'
ASSETS = APP / 'assets'
(ASSETS / 'category').mkdir(parents=True, exist_ok=True)
(ASSETS / 'products').mkdir(parents=True, exist_ok=True)

# Full transcription of the 183 catalog items (catalog page 4, 6–16).
RAW = '''
PAP-001|Papeterie & fournitures de base|Ramette papier A4 80 g — blanc|Ramette de 500 feuilles|2900
PAP-002|Papeterie & fournitures de base|Ramette papier A4 75 g|Ramette de 500 feuilles|2500
PAP-003|Papeterie & fournitures de base|Ramette papier A4 couleur (assortis)|Ramette de 500 feuilles|4500
PAP-004|Papeterie & fournitures de base|Ramette papier A3 80 g|Ramette de 500 feuilles|5800
PAP-005|Papeterie & fournitures de base|Carton papier A4 (5 ramettes)|Carton|13500
PAP-006|Papeterie & fournitures de base|Cahier 100 pages, grands carreaux|Unité|325
PAP-007|Papeterie & fournitures de base|Cahier 200 pages, grands carreaux|Unité|325
PAP-008|Papeterie & fournitures de base|Cahier travaux pratiques 100 pages|Unité|375
PAP-009|Papeterie & fournitures de base|Cahier double ligne 480 pages|Unité|80
PAP-010|Papeterie & fournitures de base|Protège-cahier (coloris assortis)|Unité|32
PAP-011|Papeterie & fournitures de base|Ardoise dure|Unité|350
PAP-012|Papeterie & fournitures de base|Enveloppes blanches format A4|Paquet|2500
PAP-013|Papeterie & fournitures de base|Enveloppes blanches format A5|Paquet|1500
PAP-014|Papeterie & fournitures de base|Étiquettes autocollantes blanches A4|Paquet de 100|2500
PAP-015|Papeterie & fournitures de base|Post-it / pense-bête 76 x 76 mm|Paquet|4000
PAP-016|Papeterie & fournitures de base|Bloc-notes A4, 50 feuilles|Unité|700
PAP-017|Papeterie & fournitures de base|Bristol couleur|Paquet|2500
PAP-018|Papeterie & fournitures de base|Papier transparent pour rétroprojection|Paquet|2500
PAP-019|Papeterie & fournitures de base|Spirales de reliure|Paquet|4000
PAP-020|Papeterie & fournitures de base|Carte d'identité scolaire|Unité|100
PAP-021|Papeterie & fournitures de base|Craie blanche lisse|Carton|16500
PAP-022|Papeterie & fournitures de base|Craie couleur lisse|Carton|32000
PAP-023|Papeterie & fournitures de base|Registre 300 pages|Unité|4500
PAP-024|Papeterie & fournitures de base|Carnet de reçus numérotés|Carnet de 50 feuillets|1600
ECR-001|Écriture & marqueurs|Stylo bille BIC bleu|Paquet de 50|2200
ECR-002|Écriture & marqueurs|Stylo bille BIC rouge|Paquet de 50|2200
ECR-003|Écriture & marqueurs|Stylo bille BIC noir|Paquet de 50|2200
ECR-004|Écriture & marqueurs|Stylo bille qualité supérieure|Unité|700
ECR-005|Écriture & marqueurs|Crayon graphite HB|Boîte de 12|1500
ECR-006|Écriture & marqueurs|Marqueur permanent|Paquet de 12|3000
ECR-007|Écriture & marqueurs|Marqueur effaçable pour tableau blanc|Boîte de 12|6000
ECR-008|Écriture & marqueurs|Surligneur fluorescent (assortis)|Boîte de 10|3500
ECR-009|Écriture & marqueurs|Correcteur liquide|Unité|1200
ECR-010|Écriture & marqueurs|Ruban correcteur|Unité|1500
ECR-011|Écriture & marqueurs|Gomme blanche|Unité|200
ECR-012|Écriture & marqueurs|Taille-crayon métallique|Unité|250
ECR-013|Écriture & marqueurs|Marqueur industriel peinture / métal|Unité|1600
CLA-001|Classement & archivage|Chemise cartonnée|Unité|70
CLA-002|Classement & archivage|Chemise cartonnée à sangle / rabat|Unité|350
CLA-003|Classement & archivage|Chemise plastique transparente|Unité|150
CLA-004|Classement & archivage|Pochette perforée plastique|Boîte de 100|2000
CLA-005|Classement & archivage|Classeur à levier A4, dos 7 cm|Unité|1500
CLA-006|Classement & archivage|Classeur à anneaux A4, dos 5 cm|Unité|1800
CLA-007|Classement & archivage|Intercalaires A4, 12 onglets|Jeu|1500
CLA-008|Classement & archivage|Parapheur 20 compartiments|Unité|5500
CLA-009|Classement & archivage|Porte-documents accordéon 13 cases|Unité|4500
CLA-010|Classement & archivage|Boîte archives carton|Lot de 10|9000
CLA-011|Classement & archivage|Boîte archives plastique avec couvercle|Unité|3600
CLA-012|Classement & archivage|Sous-chemise cartonnée|Unité|100
CLA-013|Classement & archivage|Couverture de reliure transparente A4|Lot de 100|3000
CLA-014|Classement & archivage|Porte-vues 60 vues A4|Unité|1900
CLA-015|Classement & archivage|Bannette / corbeille à courrier 3 niveaux|Unité|7500
CLA-016|Classement & archivage|Carnet de bord / main courante atelier|Unité|1800
TAB-001|Tableaux & affichage|Tableau blanc mural simple face — 60 x 90 cm|60 x 90 cm|18000
TAB-002|Tableaux & affichage|Tableau blanc mural simple face — 60 x 120 cm|60 x 120 cm|22000
TAB-003|Tableaux & affichage|Tableau blanc mural simple face — 90 x 120 cm|90 x 120 cm|28000
TAB-004|Tableaux & affichage|Tableau blanc double face à roulettes — 70 x 100 cm|70 x 100 cm|45000
TAB-005|Tableaux & affichage|Tableau blanc double face à roulettes — 90 x 120 cm|90 x 120 cm|60000
TAB-006|Tableaux & affichage|Tableau blanc double face à roulettes — 120 x 180 cm|120 x 180 cm|85000
TAB-007|Tableaux & affichage|Marqueur effaçable pour tableau|Boîte de 12|6000
TAB-008|Tableaux & affichage|Éponge / effaceur magnétique|Unité|1500
TAB-009|Tableaux & affichage|Spray nettoyant tableau blanc|Unité|2500
TAB-010|Tableaux & affichage|Panneau d'affichage en liège mural — 60 x 90 cm|60 x 90 cm|12000
TAB-011|Tableaux & affichage|Tableau de suivi / planning — 90 x 60 cm|90 x 60 cm|12000
TAB-012|Tableaux & affichage|Paperboard chevalet + bloc — 70 x 100 cm|70 x 100 cm|52000
TAB-013|Tableaux & affichage|Kakémono / roll-up publicitaire — 85 x 200 cm|85 x 200 cm|35000
TAB-014|Tableaux & affichage|Affiche sur mesure A3 (impression)|Unité|2000
TAB-015|Tableaux & affichage|Affiche sur mesure A1 (impression)|Unité|6000
TAB-016|Tableaux & affichage|Panneau de signalisation sécurité PVC — 30 x 40 cm|30 x 40 cm|8000
TAB-017|Tableaux & affichage|Panneau photoluminescent évacuation — 30 x 40 cm|30 x 40 cm|11500
TAB-018|Tableaux & affichage|Badge PVC personnalisé recto/verso|Unité|2000
TAB-019|Tableaux & affichage|Porte-badge + cordon personnalisé|Unité|1200
TAB-020|Tableaux & affichage|Tampon auto-encreur personnalisé|Unité|15000
EQP-001|Équipements & petit matériel de bureau|Agrafeuse petit modèle|Unité|2000
EQP-002|Équipements & petit matériel de bureau|Agrafeuse moyen modèle|Unité|2500
EQP-003|Équipements & petit matériel de bureau|Agrafeuse grand modèle|Unité|3500
EQP-004|Équipements & petit matériel de bureau|Agrafeuse à levier (archives)|Unité|9000
EQP-005|Équipements & petit matériel de bureau|Agrafes 26/6|Boîte de 1 000|400
EQP-006|Équipements & petit matériel de bureau|Perforatrice 2 trous|Unité|2800
EQP-007|Équipements & petit matériel de bureau|Calculatrice de bureau 12 chiffres|Unité|4000
EQP-008|Équipements & petit matériel de bureau|Ciseaux de bureau 21 cm|Unité|1500
EQP-009|Équipements & petit matériel de bureau|Cutter professionnel 18 mm + lames|Unité|1200
EQP-010|Équipements & petit matériel de bureau|Règle plastique 30 cm|Unité|350
EQP-011|Équipements & petit matériel de bureau|Tampon encreur de bureau|Unité|3000
EQP-012|Équipements & petit matériel de bureau|Encre de rechange pour tampon|Unité|1200
EQP-013|Équipements & petit matériel de bureau|Corbeille à papier|Unité|2500
EQP-014|Équipements & petit matériel de bureau|Organiseur / porte-stylos de bureau|Unité|3000
EQP-015|Équipements & petit matériel de bureau|Ruban adhésif transparent 19 mm|Lot de 10|2000
EQP-016|Équipements & petit matériel de bureau|Ruban adhésif marron 50 mm|Rouleau|1250
EQP-017|Équipements & petit matériel de bureau|Ruban de balisage au sol PVC|Rouleau de 33 m|5500
EQP-018|Équipements & petit matériel de bureau|Colle bâton 40 g|Unité|800
EQP-019|Équipements & petit matériel de bureau|Trombones petit modèle|Paquet|1500
EQP-020|Équipements & petit matériel de bureau|Trombones moyen modèle|Paquet|2000
EQP-021|Équipements & petit matériel de bureau|Trombones grand modèle|Paquet|4000
EQP-022|Équipements & petit matériel de bureau|Élastiques de bureau|Sachet de 100 g|1200
EQP-023|Équipements & petit matériel de bureau|Piles alcalines AA|Paquet de 4|1000
EQP-024|Équipements & petit matériel de bureau|Piles alcalines AAA|Paquet de 4|1000
EQP-025|Équipements & petit matériel de bureau|Machine à plastifier A4|Unité|35000
EQP-026|Équipements & petit matériel de bureau|Machine à plastifier A3|Unité|50000
EQP-027|Équipements & petit matériel de bureau|Pochettes de plastification A4|Boîte de 100|6500
EQP-028|Équipements & petit matériel de bureau|Destructeur de documents|Unité|55000
ORD-001|Ordinateurs & postes de travail|PC de bureau — Intel Core i3 / 8 Go / SSD 256 Go + écran 19"|Ensemble|185000
ORD-002|Ordinateurs & postes de travail|PC de bureau — Intel Core i5 / 8 Go / SSD 512 Go + écran 22"|Ensemble|265000
ORD-003|Ordinateurs & postes de travail|PC de bureau — Intel Core i7 / 16 Go / SSD 512 Go + écran 24"|Ensemble|375000
ORD-004|Ordinateurs & postes de travail|PC tout-en-un 23,8" — Core i5 / 8 Go / SSD 512 Go|Unité|295000
ORD-005|Ordinateurs & postes de travail|Ordinateur portable 15,6" — Core i3 / 8 Go / SSD 256 Go|Unité|195000
ORD-006|Ordinateurs & postes de travail|Ordinateur portable 15,6" — Core i5 / 8 Go / SSD 512 Go|Unité|285000
ORD-007|Ordinateurs & postes de travail|Ordinateur portable 14" ultrafin — Core i5 / 16 Go|Unité|310000
ORD-008|Ordinateurs & postes de travail|Ordinateur portable 15,6" — Core i7 / 16 Go / SSD 512 Go|Unité|425000
ORD-009|Ordinateurs & postes de travail|Écran 22" Full HD|Unité|55000
ORD-010|Ordinateurs & postes de travail|Écran 24" Full HD|Unité|70000
ORD-011|Ordinateurs & postes de travail|Station d'accueil / dock USB-C|Unité|45000
ORD-012|Ordinateurs & postes de travail|Sacoche / valise pour portable 15,6"|Unité|8000
ORD-013|Ordinateurs & postes de travail|Support surélevé pour portable|Unité|12000
ORD-014|Ordinateurs & postes de travail|Disque dur externe 1 To|Unité|40000
ORD-015|Ordinateurs & postes de travail|Disque dur externe 2 To|Unité|60000
INF-001|Imprimantes & consommables|Imprimante jet d'encre couleur|Unité|55000
INF-002|Imprimantes & consommables|Imprimante laser monochrome|Unité|95000
INF-003|Imprimantes & consommables|Imprimante multifonction laser N&B (impression / copie / scan)|Unité|145000
INF-004|Imprimantes & consommables|Imprimante multifonction laser couleur|Unité|320000
INF-005|Imprimantes & consommables|Photocopieur — toutes marques|Conditionnement non précisé|PRIX_A_SAISIR
INF-006|Imprimantes & consommables|Toner laser noir original — HP 203A (CF540A)|Unité|52000
INF-007|Imprimantes & consommables|Toner laser noir original — HP 205A (CF530A)|Unité|45000
INF-008|Imprimantes & consommables|Toner laser noir original — HP 26A (CF226A)|Unité|75000
INF-009|Imprimantes & consommables|Toner laser noir original — HP 85A (CE285A)|Unité|38000
INF-010|Imprimantes & consommables|Toner laser noir original — HP 84A (CF284A)|Unité|95000
INF-011|Imprimantes & consommables|Cartouche d'encre noire compatible (HP / Canon)|Unité|8000
INF-012|Imprimantes & consommables|Cartouche d'encre couleur compatible (HP / Canon)|Unité|10000
INF-013|Imprimantes & consommables|Toner laser noir compatible (Brother / Samsung / HP)|Unité|15000
INF-014|Imprimantes & consommables|Cartouche photocopieur RICOH MP C3003 / 3503|Unité|PRIX_A_SAISIR
INF-015|Imprimantes & consommables|Kit de maintenance / tambour|Unité|PRIX_A_SAISIR
INF-016|Imprimantes & consommables|Pochettes de plastification A4|Boîte de 100|6500
ACC-001|Accessoires informatiques & protection électrique|Clavier USB AZERTY|Unité|5000
ACC-002|Accessoires informatiques & protection électrique|Souris optique filaire USB|Unité|2000
ACC-003|Accessoires informatiques & protection électrique|Souris sans fil|Unité|5000
ACC-004|Accessoires informatiques & protection électrique|Ensemble clavier + souris sans fil|Ensemble|12000
ACC-005|Accessoires informatiques & protection électrique|Tapis de souris|Unité|800
ACC-006|Accessoires informatiques & protection électrique|Clé USB 16 Go|Unité|3000
ACC-007|Accessoires informatiques & protection électrique|Clé USB 32 Go|Unité|4000
ACC-008|Accessoires informatiques & protection électrique|Clé USB 64 Go|Unité|6500
ACC-009|Accessoires informatiques & protection électrique|Câble USB-A vers USB-B (imprimante), 1,8 m|Unité|1200
ACC-010|Accessoires informatiques & protection électrique|Câble HDMI 2 m|Unité|2500
ACC-011|Accessoires informatiques & protection électrique|Câble réseau RJ45 Cat. 6, 5 m|Unité|1800
ACC-012|Accessoires informatiques & protection électrique|Multiprise 6 prises avec interrupteur|Unité|5000
ACC-013|Accessoires informatiques & protection électrique|Onduleur 650 VA|Unité|32000
ACC-014|Accessoires informatiques & protection électrique|Onduleur 1 000 VA|Unité|55000
ACC-015|Accessoires informatiques & protection électrique|Casque-micro USB|Unité|12000
ACC-016|Accessoires informatiques & protection électrique|Webcam HD 1080p|Unité|18000
ACC-017|Accessoires informatiques & protection électrique|Vidéoprojecteur bureautique|Unité|165000
ACC-018|Accessoires informatiques & protection électrique|Écran de projection trépied — 180 x 180 cm|180 x 180 cm|65000
ACC-019|Accessoires informatiques & protection électrique|Nettoyant écran + lingettes|Unité|3000
HYG-001|Hygiène & consommables sanitaires|Papier hygiénique|Carton de 48 rouleaux|9000
HYG-002|Hygiène & consommables sanitaires|Essuie-mains|Carton|12000
HYG-003|Hygiène & consommables sanitaires|Savon liquide 5 L|Bidon|7500
HYG-004|Hygiène & consommables sanitaires|Gel hydroalcoolique 5 L|Bidon|15000
HYG-005|Hygiène & consommables sanitaires|Désinfectant surfaces 5 L|Bidon|9000
HYG-006|Hygiène & consommables sanitaires|Détergent multi-usages 5 L|Bidon|7000
HYG-007|Hygiène & consommables sanitaires|Poubelle 50 L avec couvercle|Unité|6000
HYG-008|Hygiène & consommables sanitaires|Sacs poubelle|Rouleau de 50|2500
HYG-009|Hygiène & consommables sanitaires|Balai + pelle|Ensemble|3500
MOB-001|Mobilier de bureau|Bureau droit 120 x 60 cm|Unité|55000
MOB-002|Mobilier de bureau|Bureau droit 140 x 70 cm|Unité|75000
MOB-003|Mobilier de bureau|Bureau d'angle|Unité|120000
MOB-004|Mobilier de bureau|Caisson mobile 3 tiroirs|Unité|45000
MOB-005|Mobilier de bureau|Armoire basse 2 portes|Unité|85000
MOB-006|Mobilier de bureau|Armoire haute métallique 2 portes|Unité|135000
MOB-007|Mobilier de bureau|Chaise visiteur|Unité|25000
MOB-008|Mobilier de bureau|Chaise de bureau opérateur|Unité|45000
MOB-009|Mobilier de bureau|Fauteuil de direction|Unité|95000
MOB-010|Mobilier de bureau|Table de réunion 240 x 110 cm|Unité|195000
MOB-011|Mobilier de bureau|Table pliante|Unité|35000
MOB-012|Mobilier de bureau|Vestiaire métallique 2 cases|Unité|145000
EPI-001|Équipements de protection individuelle & atelier|Gants de manutention anti-coupure|Paire|3500
EPI-002|Équipements de protection individuelle & atelier|Gants nitrile jetables|Boîte de 100|8000
EPI-003|Équipements de protection individuelle & atelier|Lunettes de protection anti-choc|Unité|3500
EPI-004|Équipements de protection individuelle & atelier|Bouchons d'oreille anti-bruit|Boîte de 50 paires|12000
EPI-005|Équipements de protection individuelle & atelier|Casque anti-bruit|Unité|18000
EPI-006|Équipements de protection individuelle & atelier|Chaussures de sécurité S3|Paire|28000
EPI-007|Équipements de protection individuelle & atelier|Masque anti-poussière FFP2|Boîte de 20|15000
EPI-008|Équipements de protection individuelle & atelier|Combinaison de travail 2 pièces|Unité|18000
EPI-009|Équipements de protection individuelle & atelier|Gilet haute visibilité|Unité|4500
EPI-010|Équipements de protection individuelle & atelier|Trousse de premiers secours réglementaire|Unité|35000
EPI-011|Équipements de protection individuelle & atelier|Extincteur — toutes capacités|Conditionnement non précisé|PRIX_A_SAISIR
'''

catalog = []
for line in RAW.strip().splitlines():
    ref, family, name, pack, price = line.split('|')
    catalog.append({
        'id': ref, 'ref': ref, 'family': family, 'name': name, 'pack': pack,
        'catalogPrice': None if price == 'PRIX_A_SAISIR' else int(price),
        'sellPrice': None,
        'source': 'catalogue', 'purchasePrice': None,
        'purchaseAlt': None, 'supplierRef': None, 'supplierNote': None,
        'stock': None, 'photo': None, 'photoKind': 'representative',
        'brand': None, 'active': True,
    })

assert len(catalog) == 183, f'catalogue attendu 183, obtenu {len(catalog)}'
# Counts from the catalogue table of contents.
expected = {'PAP':24,'ECR':13,'CLA':16,'TAB':20,'EQP':28,'ORD':15,'INF':16,'ACC':19,'HYG':9,'MOB':12,'EPI':11}
for prefix, n in expected.items():
    actual = sum(1 for p in catalog if p['ref'].startswith(prefix+'-'))
    assert actual == n, (prefix, actual, n)

# Supplier purchase-price lines from Prix imprimante.pdf.
SUPPLIER_RAW = [
(1,'HP85A',3500),(2,'HP83A',3500),(3,'HP35A',4000),(4,'HP36',4000),(5,'HP78A',4000),(6,'HP79A',4500),(7,'HP05A',5000),(8,'HP12A',4000),(9,'HP106A',6000),(10,'HP107A',6000),(11,'HP135A',13000),(12,'HP26A',8000),(13,'HP44A',5000),(14,'HP201N',7500),(15,'HP201C',7500),(16,'HP80A',5000),(17,'HP90A',17000),(18,'HP17A',5000),(19,'HP30A',6000),(20,'HP150A',9000),(21,'HP151A',14000),(22,'HP59A',15000),(23,'HP205N',7500),(24,'HP205C',7500),(25,'HP203N',7500),(26,'HP203C',7500),(27,'HP206N',14000),(28,'HP206C',14000),(29,'HP207N',13000),(30,'HP207C',13000),(31,'HP216N',11000),(32,'HP216C',11000),(33,'HP230N',18000),(34,'HP230C',18000),(35,'HP222N',18000),(36,'HP222C',18000),(37,'HP125N',7500),(38,'HP125C',7500),(39,'HP131N',7500),(40,'HP131C',7500),(41,'HP126N',7000),(42,'HP126C',7000),(43,'HP130N',7000),(44,'HP130C',7500),(45,'HP131N',7500),(46,'HP131C',7500),
(47,'HP117N',9000),(48,'HP117C',9000),(49,'HP410N',7500),(50,'HP410C',7500),(51,'HP415N',14000),(52,'HP415C',14000),(55,'HP305N',7500),(56,'HP305C',7500),(57,'HP312N',7500),(58,'HP312C',7500),(59,'HP304N',9000),(60,'HP304C',9000),(61,'HP44A',5500),(62,'HP81A',20000),(63,'HP147A',25000),(64,'HP55A',13000),(65,'TAMB19A',8000),(66,'TAMB120A',20000),(67,'CANON045N',7500),(68,'CANON045C',7500),(69,'CANON055N',13000),(70,'CANON055C',13000),(71,'CANON067N',13000),(72,'CANON067C',13000),(73,'CANON069N',14000),(74,'CANON069C',14000),(75,'CANON070',14000),(76,'CANON071',13000),(77,'CANON725',3800),(78,'CANON719',5000),(79,'CANN047',20000),(80,'CANON052',9000),(81,'CANON057',13000),(82,'CANON728',4000),(83,'CEXVV28N',17000),(84,'CEXV28C',17000),(85,'CEXV29N',17000),(86,'CEXV29C',17000),(87,'CEXV33',4000),(88,'CEXV42',4000),(89,'CEXV54',15000),(90,'CEXV60',4000),(91,'CEXV65',19000),(92,'CEXV54C',15000),
]
# Consolidate duplicate lines, preserve conflicting purchase price as an alternate.
sup = {}
for row, ref, cost in SUPPLIER_RAW:
    if ref not in sup:
        sup[ref] = {'ref':ref,'cost':cost,'alt':None,'rows':[row],'note':None}
    else:
        sup[ref]['rows'].append(row)
        if cost != sup[ref]['cost']:
            sup[ref]['alt'] = cost
            sup[ref]['note'] = 'Deux tarifs source pour cette référence: 5 000 F et 5 500 F; vérifier le fournisseur.'
        elif sup[ref]['note'] is None:
            sup[ref]['note'] = 'Référence répétée au même tarif; doublon regroupé.'
assert len(sup)==87

# Four family links to the exact catalogue lines: the two exact HP references and two near-family black toner refs.
# HP203N and HP205N remain explicitly marked as family matches to verify before commercial use.
merge = {
    'HP85A': ('INF-009', 'Correspondance exacte de référence (HP 85A / CE285A).'),
    'HP26A': ('INF-008', 'Correspondance exacte de référence (HP 26A / CF226A).'),
    'HP203N': ('INF-006', 'Correspondance de famille seulement: HP203N associé au HP 203A noir; à confirmer sur le code fabricant.'),
    'HP205N': ('INF-007', 'Correspondance de famille seulement: HP205N associé au HP 205A noir; à confirmer sur le code fabricant.'),
}
byid = {p['id']:p for p in catalog}
for ref,(catalog_id,note) in merge.items():
    p=byid[catalog_id]; row=sup[ref]
    p['purchasePrice']=row['cost']; p['purchaseAlt']=row['alt']; p['supplierRef']=ref
    p['supplierNote']=note + ((' ' + row['note']) if row['note'] else '')
    p['purchaseSourceRows']=row['rows']; p['declaredType']='Original (déclaré par l’utilisateur)'

# Add remaining priced supplier references as stock products outside the general 2026 catalog.
for ref, row in sup.items():
    if ref in merge:
        continue
    brand = 'HP' if ref.startswith('HP') else 'Canon' if ref.startswith(('CANON','CANN','CEXV','CEXVV')) else ('À confirmer' if ref.startswith('TAMB') else 'Canon / copieur')
    if ref.startswith('TAMB'):
        family='Tambours & consommables'
        name=f'Tambour / unité d’image — {ref}'
    else:
        family='Références fournisseurs — cartouches & toners'
        name=f'Cartouche / toner — {ref}'
    note = row['note']
    if ref == 'CEXVV28N':
        note = 'Code retranscrit tel qu’imprimé; « CEXVV28N » pourrait être une coquille pour CEXV28N. Vérifier la boîte.'
    if ref == 'CANN047':
        note = 'Code retranscrit tel qu’imprimé; vérifier l’orthographe CANN047 / CANON047.'
    if ref == 'HP36':
        note = 'La référence est indiquée HP36 sans suffixe A; vérifier la variante.'
    if ref in ('HP85A','HP26A','HP203C','HP205C'):
        note = (note + ' ' if note else '') + 'Le type est déclaré original, mais la référence/conditionnement et le coût sont à vérifier avant vente.'
    if not note:
        note='Référence issue de la liste de prix d’achat; prix de vente à renseigner.'
    catalog.append({
        'id':'SUP-'+ref, 'ref':ref, 'family':family, 'name':name, 'pack':'Unité',
        'sellPrice':None, 'source':'liste_fournisseur', 'purchasePrice':row['cost'],
        'purchaseAlt':row['alt'], 'supplierRef':ref, 'supplierNote':note,
        'purchaseSourceRows':row['rows'], 'stock':None, 'photo':None, 'photoKind':'web_reference',
        'brand':brand, 'declaredType':'Original (déclaré par l’utilisateur)', 'active':True,
    })

assert len(catalog)==266, f'attendu 266 produits (183 catalogue + 83 refs fournisseurs hors catalogue), obtenu {len(catalog)}'

# Reuse local category images extracted from the PDF (representative, not SKU-specific).
source_cats = ROOT/'work'/'catalog_images'
cat_src = {
    'paper': source_cats/'page04_img1.jpeg',
    'stationery': source_cats/'page04_img2.jpeg',
    'writing': source_cats/'page06_img1.jpeg',
    'filing': source_cats/'page07_img1.jpeg',
    'computer': source_cats/'page11_img1.jpeg',
    'laptop': source_cats/'page11_img2.jpeg',
    'printer': source_cats/'page12_img1.jpeg',
    'multifunction': source_cats/'page12_img2.jpeg',
    'equipment': source_cats/'page13_img1.jpeg',
}
# convert reusable category images into compact web thumbnails
for key, src in cat_src.items():
    out=ASSETS/'category'/f'{key}.jpg'
    with PILImage.open(src) as im:
        im=im.convert('RGB'); im.thumbnail((900,550),PILImage.Resampling.LANCZOS)
        im.save(out,'JPEG',quality=82,optimize=True)
category_photo={
    'Papeterie & fournitures de base':'paper',
    'Écriture & marqueurs':'writing',
    'Classement & archivage':'filing',
    'Tableaux & affichage':None,
    'Équipements & petit matériel de bureau':'equipment',
    'Ordinateurs & postes de travail':'computer',
    'Imprimantes & consommables':'printer',
    'Accessoires informatiques & protection électrique':'equipment',
    'Hygiène & consommables sanitaires':None,
    'Mobilier de bureau':None,
    'Équipements de protection individuelle & atelier':None,
    'Références fournisseurs — cartouches & toners':None,
    'Tambours & consommables':None,
}
for p in catalog:
    if p['source']=='catalogue':
        # Choose family-level photo for generic catalog products; exact toner rows use their own referenced product image below.
        if p['ref']=='INF-001': key='multifunction'
        elif p['ref']=='INF-002': key='printer'
        elif p['ref'] in ('INF-003','INF-004'): key='multifunction'
        elif p['ref'] in ('INF-006','INF-007','INF-008','INF-009'):
            key=None
        elif p['ref'].startswith('ORD-') and ('portable' in p['name'].lower() or 'sacoche' in p['name'].lower()): key='laptop'
        else: key=category_photo.get(p['family'])
        if key:
            p['photo']=f'/assets/category/{key}.jpg'
            p['photoKind']='image catalogue — famille'
    elif p['source']=='liste_fournisseur':
        p['photoKind']='photo Web indicative'

# Extract the previously researched cartridge-image map from the work script, and copy its images into this app.
photo_map={}
script_path=ROOT/'work'/'build_database.py'
if script_path.exists():
    tree=ast.parse(script_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='photo_map' for t in node.targets):
            photo_map=ast.literal_eval(node.value); break
source_img=ROOT/'image-search'
for p in catalog:
    code=p.get('supplierRef') or p['ref']
    # Product photos specific to cartridge references; use only local images already searched and screened.
    if code in photo_map:
        filename, source_url, note = photo_map[code]
        src=source_img/filename
        if src.exists():
            out=ASSETS/'products'/(re.sub(r'[^A-Za-z0-9_-]','_',code)+'.jpg')
            with PILImage.open(src) as im:
                im=im.convert('RGB'); im.thumbnail((720,500),PILImage.Resampling.LANCZOS)
                im.save(out,'JPEG',quality=78,optimize=True)
            p['photo']=f'/assets/products/{out.name}'
            p['photoKind']='photo Web indicative'
            p['photoSource']=source_url
            p['photoNote']=note

# Fill the few priced supplier references without a prior local photo with a model-specific Web image.
EXTRA_SUPPLIER_PHOTOS={
    'CANON069C':('web-CANON069C.jpg','https://www.inktechnologies.com/canon-069h-cyan-high-capacity-toner-cartridge-5097c001-genuine-oem'),
    'CANON052':('web-CANON052.jpg','https://ebay.com/p/6048821265'),
    'CEXV65':('web-CEXV65.jpg','https://www.drtusz.com/cartridges-laser-original-oem-toner-cartridge-canon-exv65-5761c001-black-printer-canon-p-18149.html'),
}
for p in catalog:
    if p['ref'] in EXTRA_SUPPLIER_PHOTOS:
        filename,source=EXTRA_SUPPLIER_PHOTOS[p['ref']]
        photo=ASSETS/'products'/filename
        if photo.exists():
            p['photo']=f'/assets/products/{filename}'
            p['photoKind']='photo Web indicative'
            p['photoSource']=source
            p['photoNote']='Photo de la référence/modèle correspondant trouvé en ligne; vérifier la boîte et le conditionnement reçus. L’image ne prouve pas l’authenticité du stock.'

# Supplier cross-reference warnings and photo source notes.
for p in catalog:
    if p.get('purchasePrice') is not None and p.get('sellPrice') is not None:
        if p['purchasePrice'] and p['sellPrice']/p['purchasePrice'] >= 5:
            extra='Écart fort entre le coût de la liste fournisseur et le prix de vente catalogue; vérifier modèle, emballage et authenticité.'
            p['supplierNote']=((p.get('supplierNote')+' ') if p.get('supplierNote') else '')+extra
    if p['source']=='catalogue':
        p['saleSource']='ESS_Catalogue_General_2026.pdf — prix indicatif HT'
    else:
        p['saleSource']='Prix de vente à saisir; absent du catalogue général pour cette référence.'

# One locally cached Web image per general-catalogue reference. Generic entries are
# labelled illustrative; the image is never treated as proof of brand / exact variant.
from urllib.parse import quote
catalogue_photo_dir=ASSETS/'catalogue'
for p in catalog:
    if p['source']=='catalogue':
        photo=catalogue_photo_dir/(p['ref']+'.jpg')
        if photo.exists():
            p['photo']=f'/assets/catalogue/{photo.name}'
            p['photoKind']='photo Web indicative'
            p['photoSource']='https://www.google.com/search?tbm=isch&q='+quote(p['name']+' '+p['family'])
            p['photoSourceKind']='image_search'
            p['photoNote']='Image Web illustrative du type de produit; elle ne confirme pas une marque, une référence fabricant, une variante ou un conditionnement.'

# Front-end categories / counts.
category_labels=[]
for p in catalog:
    if p['family'] not in category_labels:
        category_labels.append(p['family'])

payload={
    'brand':'ELMANSOUR SUPPLIES & SERVICES',
    'catalogEdition':2026,
    'currency':'FCFA',
    'taxMode':'HT',
    'catalogCount':183,
    'supplierOnlyCount':sum(1 for p in catalog if p['source']=='liste_fournisseur'),
    'productCount':len(catalog),
    'categories':category_labels,
    'products':catalog,
    'missingSupplierPriceRefs':['CEXV42GIGA','CEXV33GIGA','CEXV65GIGA','CEXV64','CEXV59','CEXV59GIGA','CEXV37','CEXV34','GR15','GPR18'],
    'notes':[
        'Les 183 références du catalogue général conservent les prix de catalogue indicatifs HT de l’édition 2026 dans catalogPrice; sellPrice reste vide pour saisie manuelle.',
        'Les prix d’achat sont renseignés uniquement lorsque la liste « Prix imprimante.pdf » donne un coût; les autres restent à compléter.',
        'Chaque référence catalogue dispose d’un visuel Web local. Les photos de produits génériques sont illustratives; les photos de consommables ne prouvent pas à elles seules la variante ou l’authenticité.',
        'Le coût d’achat de HP44A apparaît deux fois (5 000 F et 5 500 F); les deux sont conservés.',
        '10 références du PDF fournisseur sans prix d’achat sont exclues de la liste active, comme demandé précédemment.',
        'Vous avez indiqué que les références fournisseur sont originales; plusieurs coûts sont très inférieurs aux tarifs catalogue originaux. Les fiches concernées portent un avertissement à vérifier.',
    ]
}
(APP/'data').mkdir(exist_ok=True)
(APP/'data'/'catalog.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print('catalogue',sum(1 for p in catalog if p['source']=='catalogue'), 'fournisseur hors catalogue',sum(1 for p in catalog if p['source']=='liste_fournisseur'), 'total',len(catalog),'photo assets',sum(1 for p in catalog if p.get('photo')))
