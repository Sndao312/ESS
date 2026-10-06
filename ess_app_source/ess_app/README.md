# Boutique E.S.S. — vitrine headless WooCommerce

## Parcours retenu

La vitrine garde son apparence, sa navigation, ses filtres et ses fiches produit. WooCommerce reste la source de vérité pour les prix, promotions, stocks, livraison, paiement et commandes.

```text
Vitrine E.S.S. ──API same-origin──> serveur Python ──clé REST privée (lecture)──> WooCommerce
       │
       └── panier signé à usage unique ──> plugin WordPress ──> checkout natif WooCommerce
```

Le serveur revalide les produits au moment du passage au checkout, signe un jeton de panier à durée courte, puis le navigateur le transmet par formulaire POST au plugin WordPress. Le plugin reconstruit le panier dans une vraie session WooCommerce et redirige vers la page de commande WooCommerce. Le checkout natif collecte les coordonnées, calcule les taxes et frais configurés, propose les moyens de paiement actifs et crée la commande WooCommerce. La commande et son statut de paiement sont ainsi visibles dans **WooCommerce → Commandes**.

Aucune clé WooCommerce ni aucun secret de signature n’est envoyé dans le JavaScript. Le secret de transfert est partagé uniquement entre le serveur Python et `wp-config.php`.

Le mode par défaut reste `local` pour conserver l’application historique SQLite et l’aperçu du catalogue. Ce mode n’est pas un checkout de production et n’encaisse pas de paiement. Pour publier, définissez explicitement `ESS_STORE_BACKEND=woocommerce`.

## Fichiers principaux

- `server.py` — serveur HTTP, routes storefront et choix du backend.
- `woocommerce_api.py` — client REST WooCommerce v3, prix normaux/promotionnels, validation fraîche du panier et jeton de transfert signé.
- `storefront_data.py` — adaptateur d’aperçu SQLite, sans utiliser `catalogPrice` comme prix client.
- `storefront/index.html`, `storefront/styles.css`, `storefront/app.js` — boutique, filtres, fiches, panier et transfert vers le checkout natif.
- `wordpress-plugin/ess-storefront-checkout/ess-storefront-checkout.php` — plugin WordPress qui ouvre la session WooCommerce et restaure le panier.
- `tests/` — tests du client WooCommerce et des routes HTTP.
- `.env.example` — exemple de configuration sans identifiants réels.

## Aperçu local et application SQLite

Prérequis : Python 3.10+. Aucune dépendance Python externe n’est requise.

```bash
cd ess_app
python3 server.py
```

Le serveur utilise par défaut SQLite et l’interface d’administration historique est disponible à `/admin/`. La vitrine locale sert à vérifier la présentation et le catalogue; le checkout et le paiement réels nécessitent le backend WooCommerce. Un article local sans prix de vente client reste non achetable et affiche **« Prix bientôt disponible »**. Les valeurs indicatives `catalogPrice` ne sont jamais utilisées comme prix public. L’écran **Historique local** conserve les anciennes ventes/commandes SQLite et ne remplace pas le suivi des commandes de production dans WooCommerce.

Pour lancer les tests :

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py woocommerce_api.py storefront_data.py build_data.py
node --check storefront/app.js
```

## Configuration WooCommerce pour la production

### 1. Boutique, devise, taxes et pages

1. Installez WordPress sur un hébergement persistant avec HTTPS.
2. Installez et activez **WooCommerce**.
3. Dans **Réglages → Permaliens**, choisissez une structure lisible et enregistrez.
4. Dans **WooCommerce → Réglages → Général**, choisissez la devise réellement utilisée (le franc CFA BCEAO/XOF si c’est bien celle retenue par E.S.S.) et indiquez uniquement les renseignements réels de la boutique.
5. Réglez les taxes et l’affichage des prix selon la politique E.S.S.; ne présumez pas que les montants sont HT ou TTC sans vérifier ces réglages.
6. Dans **WooCommerce → Réglages → Avancé**, vérifiez que les pages Panier et Commande natives sont bien assignées.
7. Configurez les zones, méthodes et frais de livraison/retrait applicables. Le checkout natif calculera ceux que vous avez réellement configurés.

### 2. Produits et prix

Dans **Produits → Tous les produits** ou **Ajouter un produit** :

- Publiez chaque produit qui doit apparaître sur le site et vérifiez qu’il est achetable.
- Saisissez le **Prix régulier** et, si besoin, le **Prix promo** dans les champs WooCommerce. La vitrine affiche le prix WooCommerce courant; pendant une promotion active elle montre aussi le prix normal barré.
- Les modifications de prix faites dans WordPress se répercutent dans la vitrine au prochain chargement. Les sélections d’accueil peuvent rester en cache serveur environ 45 secondes.
- Si le prix WooCommerce courant est vide, la vitrine affiche exactement **« Prix bientôt disponible »** et désactive l’ajout au panier. Le serveur refuse également ce produit au moment du checkout.
- Vérifiez catégories, SKU/référence, images et stock.
- Le parcours actuel ajoute les produits simples. Les produits variables nécessitent un sélecteur de variations avant de pouvoir être achetés depuis la vitrine.
- Les 266 références SQLite ne sont pas importées automatiquement. N’utilisez pas `catalogPrice` comme prix de vente; saisissez le tarif client dans WooCommerce produit par produit.

### 3. Plugin WordPress requis pour le checkout natif

Le plugin du dépôt est nécessaire pour transférer sans CORS les articles du panier vers une session WooCommerce réelle :

1. Copiez le dossier `wordpress-plugin/ess-storefront-checkout/` vers `wp-content/plugins/ess-storefront-checkout/` (ou créez-en un ZIP et installez-le dans **Extensions → Ajouter une extension**).
2. Générez un secret aléatoire suffisamment long, par exemple avec `openssl rand -hex 32`.
3. Dans le `wp-config.php` du site WordPress, avant la ligne « That's all, stop editing », ajoutez la constante avec la valeur générée :

   ```php
   define( 'ESS_WC_HANDOFF_SECRET', 'COLLER_ICI_LE_SECRET_ALEATOIRE' );
   ```

4. Activez **E.S.S. Storefront Checkout Handoff** dans **Extensions**.
5. Utilisez exactement la même valeur pour `ESS_WC_HANDOFF_SECRET` dans l’environnement privé du serveur Python. Ne la placez jamais dans un fichier JavaScript, une page HTML ou un dépôt public.

Le jeton est signé, ne contient que les identifiants/quantités, expire après cinq minutes et ne peut être utilisé qu’une fois. Le plugin vérifie à nouveau que chaque produit est publié, simple, achetable et tarifé avant de l’ajouter au panier WooCommerce.

### 4. Moyens de paiement

Dans **WooCommerce → Réglages → Paiements** :

- Activez et configurez le ou les moyens effectivement retenus par E.S.S. (extension de passerelle installée, compte marchand, devises, identifiants et URL de retour/webhooks si demandés).
- Vérifiez que chaque méthode apparaît et fonctionne sur le checkout natif.
- Faites d’abord un test avec le mode sandbox/test de la passerelle, puis un test réel contrôlé avant l’ouverture publique.
- Vérifiez la devise autorisée par la passerelle et les notifications de paiement. La commande n’est considérée comme payée qu’après confirmation de WooCommerce/de la passerelle.

Les moyens montrés aux clients sont ceux que WooCommerce rend disponibles pour leur commande. Ce code ne simule pas un paiement et ne marque pas une commande comme payée lui-même.

### 5. Clé REST et variables d’environnement côté serveur

Dans **WooCommerce → Réglages → Avancé → API REST → Ajouter une clé** :

1. Créez un utilisateur WordPress dédié à l’intégration.
2. Créez une clé **Lecture seule** : la vitrine lit le catalogue avec la REST API; les commandes sont créées par le checkout natif WooCommerce, pas par une écriture REST.
3. Copiez les identifiants immédiatement dans le fichier privé `.env` du serveur. Révoquez toute clé exposée.

Exemple à adapter :

```dotenv
ESS_STORE_BACKEND=woocommerce
ESS_WC_SITE_URL=https://votre-site-wordpress.example
ESS_WC_CONSUMER_KEY=ck_votre_cle
ESS_WC_CONSUMER_SECRET=cs_votre_secret
ESS_WC_HANDOFF_SECRET=la_meme_valeur_que_dans_wp_config
ESS_STORE_PHONE=+221777477778
ESS_STORE_CURRENCY=FCFA
ESS_STORE_BRAND=ELMANSOUR SUPPLIES & SERVICES
```

`ESS_WC_SITE_URL` est l’URL de base WordPress, éventuellement avec son sous-dossier, sans `/wp-json`. HTTPS est obligatoire hors `localhost`. Redémarrez le serveur Python après toute modification des variables. Le fichier `.env` est ignoré par Git.

### 6. Vérification du parcours

1. Vérifiez que `GET /api/health` indique `storeBackend: "woocommerce"`.
2. Contrôlez le catalogue, une fiche avec prix normal, une fiche en promotion, une fiche sans prix et un article hors stock.
3. Confirmez que l’article sans prix affiche bien **« Prix bientôt disponible »** et que son bouton est désactivé.
4. Ajoutez un produit test tarifé, poursuivez vers WooCommerce, sélectionnez une livraison/un retrait configuré et un moyen de paiement test.
5. Vérifiez la page de confirmation WooCommerce, puis **WooCommerce → Commandes** : commande, lignes, totaux, mode de livraison et statut de paiement doivent correspondre au test.
6. Supprimez la commande de test et désactivez le mode test uniquement après les vérifications réelles.

Routes utilisées par la vitrine :

- `GET /api/store/catalog` — catégories et sélections d’accueil.
- `GET /api/store/products` — recherche, catégorie, prix, disponibilité, tri et pagination.
- `GET /api/store/products/<slug>` — fiche WooCommerce.
- `POST /api/store/checkout` — revalide les identifiants et quantités côté serveur, puis remet un jeton signé à usage unique au navigateur pour le checkout natif.

Les prix reçus du navigateur ne sont jamais utilisés pour créer les lignes de commande. WooCommerce reconstruit son panier avec ses propres produits et prix actuels, puis calcule taxes, livraison et total selon ses réglages.

## Informations non fournies et limites de validation

Le numéro de téléphone configuré est `+221 77 747 77 78`. Aucune adresse, adresse e-mail E.S.S., grille de livraison, délai ou condition de retour n’a été inventé. Complétez et validez ces informations ainsi que la politique de confidentialité avant publication.

L’aperçu disponible sur ce poste utilise SQLite et n’est pas un hébergement permanent. Je n’ai pas reçu les accès d’un véritable WordPress/WooCommerce E.S.S.; le client API et les routes sont testés localement/simulés, mais le plugin et le paiement doivent encore être installés et validés sur le site réel, notamment avec les passerelles réellement choisies.
