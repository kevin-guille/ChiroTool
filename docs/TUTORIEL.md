<div align="center">

# 🦇 ChiroTool

### Préparer, envoyer et suivre vos nuits chiroptères

*Outil libre pour le protocole **Vigie-Chiro Point Fixe** (MNHN)*

![Icône ChiroTool](captures/icon_256.png)

**Version 0.8.1** · Tutoriel utilisateur. Release GitHub : [v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1).

</div>

---

## Sommaire

1. [À quoi sert ChiroTool ?](#1--à-quoi-sert-chirotool-)
2. [Le principe en une image](#2--le-principe-en-une-image)
3. [Installation](#3--installation)
4. [Premier lancement : la configuration en 2 minutes](#4--premier-lancement--la-configuration-en-2-minutes)
5. [Comprendre l'interface](#5--comprendre-linterface)
6. [Traiter une nuit, étape par étape](#6--traiter-une-nuit-étape-par-étape)
7. [Traiter plusieurs nuits d'un coup (mode Batch)](#7--traiter-plusieurs-nuits-dun-coup-mode-batch)
8. [Valider les sons et remonter vos identifications](#8--valider-les-sons-et-remonter-vos-identifications)
9. [La synthèse d'une nuit et les niveaux d'activité](#9--la-synthèse-dune-nuit-et-les-niveaux-dactivité)
10. [Visualiser l'activité des espèces](#10--visualiser-lactivité-des-espèces)
11. [Travailler en équipe](#11--travailler-en-équipe)
12. [Questions fréquentes & dépannage](#12--questions-fréquentes--dépannage)
13. [Limites connues](#13--limites-connues)
14. [Nouveautés v0.8 / v0.7](#14-nouveautes-v08-v07)
15. [Crédits & licence](#15--crédits--licence)

---

## 1 · À quoi sert ChiroTool ?

Si vous faites du **Point Fixe Vigie-Chiro**, vous connaissez la corvée : pour
chaque nuit d'enregistrement, il faut renommer les fichiers (LupasRename),
appliquer l'expansion temporelle (Kaleidoscope), créer une participation sur le
portail Vigie-Chiro, uploader les WAV, attendre le mail de Tadarida, télécharger
le tableur, puis nettoyer les contacts inutiles à la main dans Excel.

Sur une campagne de 60 contrats × plusieurs nuits, cela représente des **journées
entières** de manipulations répétitives, sujettes aux erreurs.

**ChiroTool fait tout ça à votre place**, depuis une seule fenêtre :

| Avant (manuel) | Avec ChiroTool |
|---|---|
| LupasRename → renommer les WAV | ✅ Renommage automatique au format Vigie-Chiro |
| Kaleidoscope → expansion temporelle | ✅ TE×10 intégré (validé bit-à-bit, jusqu'à ×2 plus rapide) |
| Portail web → créer la participation | ✅ Création automatique via l'API |
| Upload manuel des fichiers | ✅ Upload parallèle (3 à 5× plus rapide) |
| Attendre le mail Tadarida | ✅ Suivi automatique, notification quand c'est prêt |
| Excel → trier les contacts à la main | ✅ Nettoyage automatique par seuils de confiance |
| Tableur de suivi à jour à la main | ✅ Registre central + export pour le suivi d'équipe |

**En résumé** : vous déposez vos dossiers de nuits, vous cliquez, et ChiroTool
gère le renommage, l'expansion temporelle, l'envoi à Vigie-Chiro, l'analyse
Tadarida, le nettoyage et le suivi. Vous gardez la main sur ce qui compte : la
**validation scientifique** des espèces.

C'est **gratuit, local et open-source**. Vos données restent chez vous (sauf les
WAV envoyés à Vigie-Chiro, comme d'habitude).

---

## 2 · Le principe en une image

```
   Retour de terrain : vous déposez vos dossiers de nuits
   sous un dossier "espace de travail" (workspace)
                          │
                          ▼
   ┌──────────────────────────────────────────────────┐
   │  ▶ PRÉPARER     renommage + expansion temporelle  │
   │  ▶ UPLOAD       envoi à Vigie-Chiro + Tadarida    │
   │  ▶ NETTOYER     purge des contacts non pertinents │
   └──────────────────────────────────────────────────┘
                          │
                          ▼
   ┌──────────────────────────────────────────────────┐
   │  🔍 VALIDER      vos identifications d'expert     │
   │       └──► ⬆ remontée vers Vigie-Chiro (1 clic)   │
   └──────────────────────────────────────────────────┘
                          │
                          ▼
   Résultats : tableur d'observations propre, synthèse
   avec niveaux d'activité, graphes, suivi de campagne
```

**Trois boutons, dans l'ordre** — puis la validation, qui est la seule étape où
votre expertise est irremplaçable. Et depuis la v0.5, vos identifications
repartent vers le portail national en un clic.

---

## 3 · Installation

ChiroTool est un **logiciel portable** : pas d'installation, pas de droits
administrateur requis.

1. Récupérez le fichier **`ChiroTool.exe`** (≈ 36 Mo) auprès de votre référent ou
   sur la [release v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1).
2. Placez-le où vous voulez (Bureau, clé USB, disque dur externe…).
3. Double-cliquez pour le lancer.

> 📸 **[Capture 01 — `ChiroTool.exe` dans l'explorateur Windows, avec son icône
> bleue]**

> **Note Windows** : au premier lancement, Windows SmartScreen peut afficher un
> avertissement (logiciel non signé). Cliquez sur **« Informations
> complémentaires »** puis **« Exécuter quand même »**. C'est normal pour un
> logiciel libre non distribué via le Microsoft Store.

### Deux modes de fonctionnement

- **Mode installé** (par défaut) : la configuration est stockée dans votre profil
  Windows (`%APPDATA%\ChiroTool\`).
- **Mode portable** : posez un fichier vide nommé `chirotool.cfg` à côté de
  l'`.exe`. La configuration sera alors stockée à côté du logiciel (pratique pour
  une clé USB qui passe d'un poste à l'autre).

---

## 4 · Premier lancement : la configuration en 2 minutes

Au tout premier démarrage, un **assistant d'accueil** s'ouvre automatiquement. Il
vous guide en 3 étapes.

> 📸 **[Capture 02 — Assistant d'accueil, étape 1 : Token Vigie-Chiro]**

### Étape 1 — Votre token Vigie-Chiro

Le **token** est votre clé d'accès personnelle à l'API Vigie-Chiro. Il permet à
ChiroTool de créer des participations et d'uploader vos enregistrements **à votre
nom**.

Pour le récupérer :

1. Cliquez sur **« 🌐 Ouvrir le portail »** et connectez-vous à Vigie-Chiro.
2. Ouvrez les outils de développement du navigateur : touche **F12** → onglet
   **Console**.
3. Cliquez sur **« 📋 Copier »** dans ChiroTool, puis collez la commande dans la
   console et appuyez sur **Entrée**.
4. Une suite de 32 caractères s'affiche. Copiez-la et collez-la dans le champ
   **Token** de ChiroTool.
5. Cliquez sur **« Tester »** : vous devriez voir *« ✓ token valide — connecté en
   tant que [votre pseudo] »*.

> 💡 Le token est valable ~30 jours. Quand il expire, refaites cette manipulation
> (Préférences → API Vigie-Chiro).

### Étape 2 — Votre dossier de travail

Choisissez (ou créez) un **dossier racine** où vous déposerez vos campagnes. Par
exemple : `D:\Chiros-2026\`. À l'intérieur, vous aurez un sous-dossier par
contrat/campagne.

C'est dans ce dossier que ChiroTool rangera son index interne et ses sauvegardes
(dans un sous-dossier `_chirotool/` qu'il ne faut pas supprimer). À cet accueil,
le dossier est scanné tout de suite. **Aux lancements suivants**, le chemin
peut être réaffiché sans scan automatique (voir [§5](#5--comprendre-linterface)
et Préférences → **Garder en mémoire le dernier dossier**).

> 📸 **[Capture 03 — Assistant d'accueil, étape 2 : Dossier de travail]**

### Étape 3 — Votre parc de matériel (optionnel mais recommandé)

Saisissez vos enregistreurs (numéro, marque, modèle, n° de série, micro…). Une
fois renseignés, ils seront proposés automatiquement dans les menus déroulants
lors de la saisie des métadonnées : plus besoin de retaper les séries à chaque
nuit, et **zéro faute de frappe**.

> 📸 **[Capture 04 — Préférences → onglet « Mes matériels »]**

> 💡 **Astuce équipe** : si votre structure a déjà un fichier de parc
> (`materiels.json`), posez-le simplement dans votre dossier de travail :
> ChiroTool vous proposera de l'importer automatiquement au premier scan.

---

## 5 · Comprendre l'interface

> 📸 **[Capture 05 — Fenêtre principale : barre du haut, liste des sessions à
> gauche, onglets à droite]**

La fenêtre se compose de trois zones :

**① La barre du haut** — choisir le dossier de travail (`Parcourir…`), le
scanner (`🔄 Scanner`), accéder aux préférences (`⚙`) et aux informations
(`ℹ`). Aux lancements suivants, ChiroTool **ne rescane pas** tout seul le
dernier dossier (un SSD EXFAT endormi bloquait l'interface). Si
**Préférences → Général → Garder en mémoire le dernier dossier** est coché
(défaut), le chemin est réaffiché : `Scanner` pour le recharger, `Parcourir`
pour un autre. Décochez la case pour partir de `(aucun)`.

**② La liste des sessions (à gauche)** — toutes vos nuits, regroupées par
campagne. Une pastille de couleur indique l'état de chaque nuit :

| Pastille | Signification |
|---|---|
| 🔴 rouge | Brut (rien n'a encore été fait) |
| 🟡 jaune | En cours de traitement |
| 🟠 orange ⏳ | Participation connue mais tableur d'observations pas encore local — **à reprendre** (Upload, ou **🔧 Vérifier / Réparer**) |
| 🟢 vert | Nuit complètement traitée |

**③ Le panneau de détail (à droite)** — 6 onglets :

- **Vue session** : les infos de la nuit sélectionnée, le bilan de validation
  (`X / Y` contacts avec taxon observateur) + la barre d'actions
- **Registre** : toutes vos nuits, toutes campagnes confondues (suivi global)
- **Historique** : la chronologie des opérations faites sur une nuit
- **Carte** : vos points sur fond OpenStreetMap / IGN
- **Dashboard** : statistiques transverses de vos campagnes
- **Activité** : graphes ChiroTool par tranche horaire ; filtres **Chiros seulement**,
  **Taxons observateur** et **Interprétation _Vu (ChiroSurf)** (relecture d'un
  fichier déjà produit dans ChiroSurf, y compris à la racine de la session)

### La barre d'actions

En bas de la **Vue session**, une **seule ligne**. Si l'écran est trop étroit,
faites glisser la barre vers la droite (molette ou curseur sous les boutons) :

> **▶ Préparer** · **☁ Upload** · **🔧 Vérifier / Réparer** · **🔍 Valider** ·
> **🧹 Nettoyer** · **📊 Synthèse** · **🌊 ChiroSurf nuits** · **✎ Métadonnées** ·
> **📍 Carte** · **⋯ Détails**

Les libellés sont volontairement courts : **passez la souris sur un bouton** pour
lire ce qu'il fait exactement.

Deux repères visuels vous guident :

- **L'étape à faire maintenant** est en **bleu et en gras**.
- Les étapes **pas encore possibles** sont **grisées** (inutile de chercher à
  nettoyer une nuit qui n'a pas encore été analysée).

---

## 6 · Traiter une nuit, étape par étape

Prenons un exemple concret : vous revenez du terrain avec une nuit d'un SM Mini.

### Étape 0 — Déposer les fichiers

Copiez votre dossier de nuit dans votre dossier de travail, sous le bon contrat :

```
D:\Chiros-2026\
└── Contrat_1\                 ← le contrat (nom de votre choix)
    └── 19052026_260155_22_Z6\  ← votre dossier de nuit (peu importe le nom exact)
        ├── 2MU05451_Summary.txt
        └── Data\
            ├── 2MU05451_20260519_203704.wav
            ├── 2MU05451_20260519_203711.wav
            └── ...
```

### Étape 1 — Scanner

Dans ChiroTool, vérifiez que le dossier de travail est le bon, puis cliquez sur
**« 🔄 Scanner »**. Vos nuits apparaissent dans la liste de gauche.

Cliquez sur votre nuit : son détail s'affiche à droite. Une fois le tableur
d'observations récupéré, le bloc **Détection** montre aussi
**« Validation : X / Y contacts (taxon observateur) »** (et, s'il y a déjà eu
un envoi, le nombre d'identifications remontées à Vigie-Chiro). Inutile d'ouvrir
**🔍 Valider** juste pour ce décompte.

> 📸 **[Capture 06 — Vue session : progression du pipeline et barre d'actions]**

### Étape 2 — Préparer (renommage + expansion temporelle)

Cliquez sur **« ▶ Préparer »**.

ChiroTool va d'abord chercher à **deviner automatiquement** les métadonnées de la
nuit (site, point, passage, enregistreur…) à partir du nom du dossier, des noms
de WAV (Wildlife, AudioMoth expandé, Titley Swift/Ranger), du fichier
`Summary.txt` et de votre tableur de suivi. Si le Summary **ne correspond pas**
aux WAV (carte SD non formatée : l'ancienne nuit reste dans le Summary), un
**avertissement** s'affiche : la date retenue est celle des fichiers.

- **Si tout est trouvé** : une fenêtre de confirmation s'affiche, vous validez.
- **Si une info manque** : l'assistant de saisie des métadonnées s'ouvre.

> 📸 **[Capture 07 — Assistant « Métadonnées de la session »]**

Dans cet assistant :

- **Points récents** : libellés parlants (*commune · Zx · carré*), dernier choix
  carte (badge ★), points d’**autres observateurs** déjà réutilisés.
- **🗺️ Choisir sur la carte…** : ouvre la carte en mode *choix de point*
  (recherche commune, vos points dans un rayon de **5 km**, ou
  **➕ Ajouter un point** / réutilisation). Au retour, **carré + point** sont
  remplis et les **GPS** sont mémorisés pour cette session.
- **Contrat** : le nom du projet (un bouton ▾ propose ceux déjà saisis)
- **Date de début** : la date de pose (un bouton 📅 ouvre un calendrier)
- **N° site Tadarida** : les 6 chiffres du carré (saisie manuelle si besoin)
- **Point** : Z1, A2, etc.
- **Passage** : 1, 2…
- **N° enregistreur** : choisissez-le dans la liste (il remplit automatiquement
  la série et le micro depuis votre parc « Mes matériels »)

> 💡 **Astuce** : créez ou réutilisez un point une fois (carte ou pick depuis
> les meta) → il devient le *point actif*. Au « Préparer » suivant, carré et
> point sont préremplis. Sur la fiche d’un marker : **« ★ Utiliser pour la
> prochaine préparation »** (bouton toujours visible en bas de la fiche).
>
> **📍 Carte** (barre d’actions) = mode **FOCUS** : zoom sur le point de la
> nuit (pin rose `★ Z1`, ou `★ Z1 · 3 nuits` s’il y a plusieurs sessions sur
> le même point). Les GPS viennent d’abord du **manifest** de la session.
>
> Sur l’onglet Carte, **🔄 Recharger sites**, **Mes sites** ou **France**
> quittent le FOCUS et montrent **tous** vos sites (vue d’ensemble).

Cliquez sur **« Valider »**.

ChiroTool exécute alors :
1. Le **renommage** des WAV au format Vigie-Chiro (`Car260155-2026-Pass1-Z6-…`)
2. L'**expansion temporelle ×10** (création du dossier `Data_k/`) : chaque
   fichier est découpé en tranches de **5 secondes** (temps brut), comme
   Kaleidoscope. Un WAV déjà en 5 s reste un fichier ; un WAV plus long
   (Anabat Swift / Ranger jusqu'à 15 s, par exemple) sort en plusieurs WAV
   (nouveau timestamp toutes les 5 s). **Tout le son est conservé**, ce
   n'est pas un prélèvement des 5 premières secondes. Le protocole Point
   Fixe règle en général les SM4 sur 5 s : dans ce cas le nombre de
   fichiers ne change pas. Si l'Historique affiche moins d'écrits que de
   segments prévus, relancez Préparer (voir [§12](#12--questions-fréquentes--dépannage)).

Une **barre de progression** vous indique l'avancement en temps réel.

> 📸 **[Capture 08 — Fenêtre de progression avec la barre et l'ETA]**

### Étape 3 — Upload + Tadarida

Cliquez sur **« ▶ Upload + Tadarida »**.

Un **assistant de participation** s'ouvre tout de suite (le formulaire
n'attend pas le scan des WAV). Il pré-remplit ce qu'il **sait réellement** :
log Titley (`Recording start` / `stop`, T° de la nuit) s'il est dans la
session, sinon les T° du `Summary.txt`, le matériel depuis votre parc, les
dates du Summary **si c'est une seule nuit**. Si le Summary ne correspond
pas aux WAV, un **avertissement** le dit : dates (et T° sur la fenêtre des
fichiers) prises sur les WAV. Vous pouvez encore corriger ; une
participation déjà créée au mauvais jour n'est pas réutilisée.

> 📸 **[Capture 09 — Assistant « Nouvelle participation Vigie-Chiro »]**

- **Conditions météo** (optionnel) : températures (log Titley ou
  `Summary.txt`), vent, couverture nuageuse
- **Matériel** : détecteur (et n° de série envoyé à Vigie-Chiro), micro, hauteur
- Complétez ce qui est utile, puis **« Valider »**.

> 💡 **Météo non bloquante** : vent et couverture ne sont **pas** mesurés par
> les enregistreurs. Vous pouvez les laisser à **« — à renseigner — »** et
> uploader quand même — le portail web permet de les compléter **après**
> l'analyse. Les températures du Summary sont préremplies quand le fichier
> est présent ; sans Summary, les laisser vides est accepté.

> ⚠️ **Ce que ChiroTool ne fait volontairement pas** : inventer une valeur à votre
> place. Les listes vent / couverture démarrent sur **« — à renseigner — »**
> plutôt que sur « nul » ou « 0-25 » par défaut. C'est délibéré : ces données
> partent sur le portail national **à votre nom**. Mieux vaut un champ vide
> qu'une fausse observation pré-cochée et jamais relue.

ChiroTool enchaîne alors **trois phases automatiques** :

1. **Upload** — envoi des WAV vers Vigie-Chiro (en parallèle, donc rapide).
2. **Attente Tadarida** : l'analyse tourne **sur les serveurs Vigie-Chiro**.
   Cela peut prendre de quelques minutes à quelques heures. **Vous pouvez fermer
   la fenêtre dès l'envoi** : **« 🔌 Arrière-plan »** (ou la croix). Recliquer
   **Upload** sur la même nuit **rouvre le suivi**. L'analyse continue
   côté serveur.
3. **Téléchargement** — dès que c'est prêt, le tableur d'observations est récupéré
   automatiquement.

> 💡 **Si vous avez fermé l'app** : il suffira de re-cliquer « Upload + Tadarida »
> plus tard. ChiroTool détecte que la participation existe déjà, ne ré-uploade
> rien d'inutile, et récupère directement le résultat.

#### Connexion instable, analyse forcée sur le web, pastille ⏳ bloquée

Parfois l'upload s'interrompt, ou vous avez **lancé l'analyse Tadarida à la main**
sur le portail Vigie-Chiro alors que ChiroTool n'a pas encore le tableur local.
La pastille reste **orange ⏳** et l'état d'avancement ne se met pas à jour tout
seul.

1. Ouvrez la nuit concernée (une seule nuit à la fois).
2. Cliquez sur **« 🔧 Vérifier / Réparer »** (bouton orange quand la nuit est en ⏳).
3. ChiroTool **diagnostique d'abord** (aucune modification) et affiche un
   **rapport détaillé** (utile à copier dans une issue GitHub) : couverture
   Data_k ↔ serveur, état Tadarida, xlsx, flags, erreurs API.
4. Selon le cas, vous pourrez **confirmer explicitement** :
   - aligner le flag « uploadé » si tous les WAV **locaux restants** sont en ligne ;
   - **télécharger le xlsx** si l'analyse est terminée côté serveur ;
   - **relancer Tadarida** (double confirmation). Y compris si le portail
     n'arrive pas à *lister* les fichiers, mais que ChiroTool a vérifié qu'ils
     sont **déjà enregistrés** (code 409 : l'envoi a déjà eu lieu).
5. Si des WAV **encore présents dans Data_k** manquent vraiment sur le serveur,
   l'outil propose de reprendre via **« ☁ Upload »**. Les fichiers déjà
   enregistrés (code 409) sont sautés, Tadarida peut partir ensuite.

> 💡 **Après une coupure** : un re-clic **Upload** suffit souvent. Si l'app
> affiche encore des échecs ou refuse de lancer Tadarida, passez par
> **🔧 Vérifier / Réparer**. Si Tadarida sort **0 contact** alors que la nuit
> n'était pas silencieuse, le son n'est probablement pas arrivé sur le
> serveur : il faut une **nouvelle participation** et renvoyer `Data_k/`.

> 💡 **Après nettoyage** : des fichiers peuvent rester « sur le serveur seulement »
> (ex. 185 purgés localement). C'est **normal**, seuls les WAV encore dans
> `Data_k/` comptent pour la couverture 100 %.

> ⚠️ **Token API** : si le token est expiré (HTTP 401), le listing serveur
> échoue. Le diagnostic le signale clairement et **ne propose pas** un
> re-upload massif de tout Data_k. Allez dans **Préférences → API Vigie-Chiro**,
> collez un nouveau token (F12 sur le portail), puis relancez le diagnostic.
> Avec un bon token, le listing de milliers de fichiers peut prendre
> **quelques dizaines de secondes** (pagination API) — c'est attendu.

> 🛡️ **Une nuit à la fois** — pour ne pas saturer les serveurs.

### Étape 4 — Nettoyer

Une fois le tableur récupéré, cliquez sur **« 🧹 Nettoyer »** (à **droite** de
**🔍 Valider** : vous pouvez identifier d'abord, puis purger). Le bouton reste
grisé tant que Tadarida n'a pas rendu le tableur.

ChiroTool applique vos **seuils de confiance** (réglables dans Préférences →
Nettoyage) pour décider quels WAV garder :

> 📸 **[Capture 10 — Préférences → onglet « Nettoyage »]**

- Un **contact** est conservé si sa probabilité Tadarida ≥ votre seuil pour ce
  groupe (chiros, orthos, etc.).
- Un **fichier WAV** est gardé dès qu'**au moins un** de ses contacts est conservé
  (règle « OR »).
- Les contacts classés **« noise »** par Tadarida sont toujours supprimés.
- Les **validations humaines** (si vous avez déjà validé via ChiroSurf) sont
  **prioritaires** sur les seuils.

#### Rien n'est supprimé sans que vous l'ayez vu

Le nettoyage efface des WAV : c'est irréversible. ChiroTool procède donc
**toujours en deux temps**.

1. **Simulation** — une fenêtre « Analyse du nettoyage » calcule ce qui *serait*
   supprimé, **sans rien toucher**.
2. **Récapitulatif chiffré** — vous voyez exactement :

   > *« 182 / 255 WAV seront supprimés (~712 Mo). Cette action est irréversible.
   > Continuer ? »*

   Le bouton par défaut est **Non** : une validation distraite ne supprime rien.

3. **Suppression** — seulement après votre confirmation explicite.

> 🛡️ **Double garde-fou** : si plus de **80 %** des WAV allaient disparaître
> (seuil mal réglé, mauvais tableur…), une **seconde confirmation** distincte est
> demandée. C'est le cas légitime d'une nuit très bruitée — mais aussi le
> symptôme classique d'une erreur de réglage.

À la fin, un **récapitulatif visuel** s'affiche : volume avant/après, espace
disque libéré, et la possibilité de supprimer aussi les WAV bruts d'origine
(`Data/`) si vous voulez libérer encore plus de place.

> 📸 **[Capture 11 — Récapitulatif du nettoyage avec le graphe avant/après]**

✅ **La nuit est traitée.** La pastille passe au vert.

---

## 7 · Traiter plusieurs nuits d'un coup (mode Batch)

Vous avez 10 nuits à traiter ? Pas besoin de les faire une par une, et
**pas besoin de lancer plusieurs fois** ChiroTool : le Batch enchaîne les
nuits dans **une** instance.

1. En haut de la liste des sessions, cliquez sur **« ☐ Batch »**.
2. Des **cases à cocher** apparaissent sur chaque nuit. Cochez celles à traiter.
3. Cliquez sur l'action voulue : **▶ Préparer**, **▶ Upload** ou **▶ Nettoyer**.

> 📸 **[Capture 12 — Mode Batch activé, plusieurs nuits cochées + barre
> d'actions]**

ChiroTool traite alors **toutes les nuits sélectionnées** :

- Pour la **préparation** et le **nettoyage** : une nuit après l'autre.
- Pour l'**upload** : les envois s'enchaînent, puis **toutes les analyses Tadarida
  attendent en parallèle** (le serveur travaille sur plusieurs nuits à la fois).
  Chaque nuit terminée récupère son tableur dès qu'il est prêt.

Vous pouvez **fermer l'application** pendant l'attente : les analyses continuent
côté serveur. Au retour, relancez « Upload » sur les nuits concernées (ou utilisez
« 🔄 Sync API » dans le Registre) pour récupérer les résultats.

Le batch **n'ouvre pas** l'assistant métadonnées. Une nuit sans carré / point
(jamais préparée à la main) est **ignorée**. En **0.8.1**, le bilan pouvait
quand même afficher OK alors que les fichiers n'avaient pas été renommés
(surtout vers la fin d'une série d'une quinzaine). Contrôle : les noms dans
le dossier. Si rien n'a bougé, **▶ Préparer** cette nuit **seule** (l'assistant
peut saisir le carré / point), puis relancer le batch.

---

## 8 · Valider les sons et remonter vos identifications

L'identification de Tadarida est automatique. ChiroTool prépare les fichiers,
les envoie, suit l'analyse et archive. Deux usages restent **distincts** :

- **Dans ChiroTool, en option** : une validation contact par contact, puis
  l'envoi de ces identifications vers le portail. Ce n'est pas la procédure
  de validation Vigie-Chiro.
- **Dans ChiroSurf, logiciel tiers, en option** : la procédure de validation
  Vigie-Chiro. ChiroTool peut préparer un CSV par nuit et l'ouvrir dans
  ChiroSurf. Il ne fait pas cette validation.

### A · Validation contact par contact (ChiroTool, optionnelle)

1. Sur une nuit dont le tableur est récupéré, cliquez sur **« 🔍 Valider »**.
2. Un tableau filtrable des contacts s'affiche :
   - **Clic sur un en-tête** pour trier (A–Z ou petit–grand). Un 2e clic inverse ;
     un 3e revient à l'ordre d'origine. Pratique pour ramener en haut les plus
     fortes probas d'une espèce.
   - **« Taxon observateur renseigné uniquement »** : n'afficher que les lignes
     déjà validées (à la place de « Non validés seulement », les deux cases ne
     se cumulent pas).
   - **« Chiros seulement »** : masquer orthoptères, bruit, oiseaux.
   - **CSV nuits** : ouvre la fenêtre **🌊 ChiroSurf nuits** (préparer un CSV
     par nuit pour ChiroSurf, optionnel). Ce n'est pas la Synthèse, et ce
     n'est pas la validation.
3. Sélectionnez un contact, puis :
   - Utilisez les **raccourcis clavier** `O` / `P` / `S` pour indiquer votre
     niveau de confiance (pOssible / Probable / Sûr).
   - **Double-cliquez** (ou **Ouvrir le son**) pour écouter le WAV dans le
     logiciel indiqué dans Préférences → Outils. C'est une écoute, pas une
     validation. ChiroSurf peut être ce logiciel.
4. Vos validations sont sauvegardées dans un nouveau tableur suffixé de vos
   initiales (ex : `…_AB.xlsx`). Un bandeau **« ● modifications non
   enregistrées »** (titre + bouton *Enregistrer* orangé) vous rappelle de
   sauvegarder ; il disparaît après enregistrement.

> 📸 **[Capture 14 — Vue de validation : la saisie guidée (✓ connu), le bouton
> « Monter au genre » pour les sons incertains, et « Envoyer » qui remonte vos
> identifications vers Vigie-Chiro.]**

**📊 Synthèse** est le récapitulatif ChiroTool. **🌊 ChiroSurf nuits** est un
pont optionnel vers ChiroSurf. Ce ne sont pas deux étapes d'une même validation.

| | **📊 Synthèse** | **🌊 ChiroSurf nuits** |
|---|---|---|
| Pour qui | Récapitulatif de campagne | Personnes qui valident dans ChiroSurf |
| Rôle | Comptages et graphes ChiroTool | Préparer un CSV par nuit pour l'ouvrir dans ChiroSurf |
| Où se fait la validation Vigie-Chiro ? | Pas ici | Dans ChiroSurf |

### Règle de la nuit (ne plus la recasser)

Une **nuit d'enregistrement** va de **midi à midi**, pas de minuit à minuit.

| Situation | Combien de nuits | Menu **Nuit** dans Synthèse |
|---|---|---|
| Pose **21 h le 16 → 6 h le 17** | **1** (nuit du 16) | **absent** |
| Deux soirs (16 au soir **et** 17 au soir) | **2** | Nuit 1 / Nuit 2 |
| Découpage calendaire 16 / 17 à **minuit** | **interdit** | — |

Le matin du 17 (2 h, 6 h…) appartient à la nuit commencée le 16 au soir.
Deux lignes n'apparaissent que s'il y a une **deuxième soirée** (fichiers
**après midi** le second jour).

### B · Préparer un CSV par nuit pour ChiroSurf (optionnel)

Si vous **n'utilisez pas** ChiroSurf : ignorez cette section. Le récapitulatif
ChiroTool est **📊 Synthèse**
([§9](#9--la-synthèse-dune-nuit-et-les-niveaux-dactivité)).

La procédure de validation Vigie-Chiro se fait **dans ChiroSurf**. ChiroTool
ne la lance pas et ne la refait pas. Il peut seulement préparer un CSV par
nuit biologique, puis ouvrir ce CSV dans ChiroSurf. ChiroSurf travaille sur
une **nuit unique** : d'où la découpe.

1. Cliquez sur **« 🌊 ChiroSurf nuits »** (aussi depuis **🔍 Valider** →
   **CSV nuits**). Inutile pour la Synthèse.
2. ChiroTool crée le dossier `chirosurf/` et un CSV **par nuit biologique**
   (coupure à **midi**, pas à minuit) :
   `Nuit1_<nom-du-tableur>-observations.csv`, `Nuit2_…`, etc.

   | Libellé | Fichiers concernés |
   |---|---|
   | **16/07 · Nuit 1** | de **midi le 16** à **midi le 17** (soirée du 16 **et** matin du 17) |
   | **17/07 · Nuit 2** | à partir de **midi le 17** |

   Le nom du dossier session (`20260716_site…`) est la **date de début** de
   la participation, pas le nombre de nuits. Une pose d'un soir qui passe
   **minuit** reste **une** ligne. Deux lignes = fichiers **après midi** le
   lendemain (deuxième soirée, relevé tardif, carte SD non formatée).
3. **Ouvrir dans ChiroSurf** ouvre le CSV **brut** (sans `_Vu`) dans
   ChiroSurf. C'est là que se fait la validation. ChiroSurf 4.x cherche les
   sons **dans le même dossier** que le tableur : ChiroTool **copie** donc
   le CSV dans `Data_k/` (sinon `Data/`) avant l'ouverture. S'il n'y a plus
   de WAV (nuit déjà nettoyée), l'ouverture est refusée avec un message.
4. Après la validation dans ChiroSurf, le fichier `…_Vu.csv` apparaît
   **à côté** du CSV ouvert (donc dans `Data_k/`). ChiroTool le
   **rapatrie** vers `chirosurf/`. **📈 _Vu** rouvre ce fichier. Pour
   poursuivre la validation, rouvrez toujours le CSV **sans** `_Vu`
   **dans ChiroSurf**.
   Un `_Vu` déjà produit (nomenclature `Nuit_1_…` ou collé à la main dans
   `chirosurf/` / `Data_k/`) est reconnu.
5. **📊 Synthèse** peut relire ce `_Vu`. Cochez **« Interprétation _Vu
   (ChiroSurf) »**. C'est une relecture du fichier produit dans ChiroSurf
   (bandes de confiance Tadarida), pas une validation faite par ChiroTool.
   La case « identifications validées seulement » reste les lignes
   **écoutées**. La même case existe dans l'onglet **Activité** : les
   totaux du graphe suivent alors cette relecture. Les deux cases
   s'excluent. Voir issue
   [#7](https://github.com/kevin-guille/ChiroTool/issues/7).

> ⚠️ Les CSV bruts peuvent être **régénérés** (bouton dans la fenêtre) ; les
> `_Vu` ne sont **jamais** écrasés automatiquement.

> 💡 La validation contact par contact (**🔍 Valider**) reste disponible.
> Elle est distincte de la procédure ChiroSurf.

### Saisir une espèce : le champ vous guide

Quand vous tapez un taxon, ChiroTool **propose les espèces au fur et à mesure**
(par code ou par nom français : tapez `orei`, vous obtenez les Oreillards).

Un indicateur vous dit si le code est **accepté par le serveur** Vigie-Chiro :

| Indicateur | Signification |
|---|---|
| ✓ connu | Le code existe côté Vigie-Chiro, il pourra être envoyé |
| ⚠ inconnu | Le code n'est pas reconnu par le portail — il **ne partira pas** |

> 💡 C'est utile : le portail n'accepte qu'une **partie** des codes produits par
> Tadarida. Vous le voyez maintenant *au moment de la saisie*, plus au moment de
> l'envoi.

### Un son incertain entre deux espèces ? Montez au genre

Cas classique : Oreillard roux ou Oreillard gris, impossible de trancher.
Plutôt que de forcer une espèce, sélectionnez la ligne et cliquez sur
**« ↑ Monter au genre (incertain) »** : ChiroTool bascule sur *Oreillard sp.*
Idem pour les Murins (*Myotis sp.*) et les Pipistrelles (*Pipistrellus sp.*).

Le bouton ne propose que les genres réellement reconnus par le portail : pour une
espèce sans ambiguïté possible (la Barbastelle, seule de son genre en France), il
vous le dira.

### ⬆ Remonter vos identifications vers Vigie-Chiro

**C'est la grande nouveauté de la v0.5.** Vos validations ne restent plus dans
votre coin : elles repartent sur le portail national, sans aucune re-saisie web.

- **Sélectionnez des lignes** → le bouton devient *« ⬆ Envoyer la sélection (N) »*
- **Ne sélectionnez rien** → il devient *« ⬆ Envoyer tout (M) »*

Une **pastille** dans la colonne de gauche vous indique l'état de chaque contact :

| Pastille | État |
|---|---|
| ○ gris | Validé, pas encore envoyé |
| ● vert | Envoyé à Vigie-Chiro |
| ● orange | Modifié depuis l'envoi — à renvoyer |
| ● rouge | Échec de l'envoi |

*(Passez la souris sur une pastille pour lire sa signification.)*

En bas, un compteur suit l'avancement : **« ⬆ 12 / 15 identifications envoyées »**.
Le Registre affiche aussi, par nuit, ce qui reste à remonter.

> 💡 **Une identification n'est envoyable qu'avec un taxon ET une confiance** —
> c'est ce qu'exige le portail.

> 🌍 **Pourquoi ça compte** : en pratique, la quasi-totalité des observateurs
> garde ses identifications pour soi. Or ce sont précisément ces validations
> humaines qui améliorent l'apprentissage de Tadarida et le référentiel national.
> Les remonter ne vous coûte qu'un clic et profite à toute la communauté.

> ⚠️ **Effacer une identification déjà envoyée** ne la retire pas du serveur (une
> donnée ne se supprime pas côté observateur). ChiroTool vous le signale au lieu
> de faire disparaître la pastille en silence.

> ⚡ **Validation en lot** : sélectionnez **plusieurs lignes** (Ctrl+clic, ou
> Maj+clic pour une plage), puis appliquez une espèce d'un coup (champ *Taxon* +
> « Appliquer ») ou validez tout le lot avec `O`/`P`/`S` (chaque ligne reçoit
> alors son propre taxon Tadarida). Idéal pour valider rapidement une nuit
> entière d'une même espèce.

> 🧹 **Masquer les sons supprimés au nettoyage** : si vous validez *après* avoir
> nettoyé, cochez cette case (elle s'active automatiquement) pour n'afficher que
> les contacts dont le WAV existe encore. La **liste des taxons** se met aussi à
> jour selon les filtres actifs (proba, masquage, taxon observateur) : seuls les
> taxons encore présents sont proposés.

> 💡 Si vous nettoyez **après** avoir validé, vos décisions humaines sont
> respectées : un faux « noise » que vous avez corrigé en *Pipistrelle* sera
> conservé.

---

## 9 · La synthèse d'une nuit et les niveaux d'activité

Sur une nuit dont le tableur est récupéré, le bouton **« 📊 Synthèse »** ouvre le
récapitulatif ChiroTool par espèce : combien de contacts, combien de fichiers,
et une classe d'activité. ChiroSurf n'est pas nécessaire pour ce récapitulatif.
Ces classes sont une aide de lecture dans ChiroTool. Ce n'est pas l'évaluation
d'activité de ChiroSurf.

Une pose qui **passe minuit** (soir + matin) reste **une** nuit : pas de menu
Nuit. Le menu n'apparaît que si la participation couvre **plusieurs soirs**
(coupure à midi). Les classes d'activité (contacts/nuit) ne s'affichent que
**nuit par nuit**. Un `_Vu` ChiroSurf, s'il existe, est utilisé pour cette nuit ;
sinon le tableur Tadarida suffit.

> 📸 **[Capture 15 — Synthèse d'une nuit : le niveau d'activité par espèce
> (colonne de droite) et le sélecteur « Milieu » qui affine le référentiel.]**

### Ce que vous lisez

En haut : **« X contacts détectés · Y identifiés (validés) · Z espèces de chiros »**,
plus la **source** (xlsx de la nuit, ou `_Vu` si vous avez validé dans ChiroSurf).

Filtres utiles :

- **« Identifications validées seulement »** : ne compter que les lignes où
  **taxon observateur** est renseigné (ignore Tadarida seul). Après un `_Vu`
  ChiroSurf, ce sont les contacts **écoutés**.
- **« Interprétation _Vu (ChiroSurf) »** : relit un fichier `_Vu` déjà
  produit dans ChiroSurf (bandes de confiance Tadarida, pas le temps).
  ChiroTool n'applique pas la procédure de validation. Distinct de
  « validées seulement ». Les deux cases s'excluent. L'export CSV ajoute
  alors `Atteint_75`, `F75`, la taille du pool Tadarida et le nombre de
  **proba illisibles** (hors pool ; virgule ou point acceptés). Une colonne
  **Seuil _Vu** indique si le seuil de l'espèce est atteint.
  Un `_Vu` illisible ou sans les colonnes Vigie-Chiro affiche le nom du
  fichier et replie sur le tableur. Si la source n'est pas un `_Vu`, un
  avertissement le rappelle : cette relecture vise un fichier produit dans
  ChiroSurf, pas une validation contact par contact.
  En cumul multi-nuits, le calcul se fait **nuit par nuit** puis s'additionne
  (pas de classe d'activité sur le cumul). L'onglet **Activité** a la même
  case. Voir issue
  [#7](https://github.com/kevin-guille/ChiroTool/issues/7).
- **« Chiros seulement »** : masquer orthoptères, bruit, oiseaux.
- **« Proba Tadarida ≥ »** : seuil optionnel (ex. `0.5` ou `50`) pour la synthèse
  **non validée** ; les lignes déjà validées par l'observateur passent toujours.
  Désactivé si « Interprétation _Vu (ChiroSurf) » est cochée.

Pour chaque espèce, une colonne **Activité** indique :

| Classe | Lecture |
|---|---|
| Faible | sous le quart des nuits de référence |
| Moyenne | dans la norme |
| Forte | parmi le quart haut |
| Très forte | parmi les 2 % de nuits les plus actives |

### D'où viennent ces seuils

Du **référentiel national Vigie-Chiro**, construit sur des milliers de nuits du
même protocole. ChiroTool situe votre nombre de contacts dans la distribution de
référence **de cette espèce**, et en déduit la classe.

Le contexte est **déduit automatiquement** : la **saison** depuis la date de la
nuit, la **région** depuis votre n° de site. Vous pouvez affiner avec le menu
**« Milieu »** (forêt, agricole, urbain…) qui correspond au **contexte général
autour du point**. Si une déclinaison est trop peu échantillonnée pour être
fiable, ChiroTool **revient tout seul** au référentiel national et l'indique.

> 📊 Le référentiel utilisé est affiché en bas de la fenêtre (ex. *« été ·
> Occitanie »*), et l'export CSV le reprend — pour que votre rapport soit traçable.

### ⚠️ Trois choses à ne jamais oublier

1. **On ne compare pas les contacts entre espèces.** Un Grand rhinolophe
   s'entend à ~5 m, une Noctule à plus de 100 m. 20 contacts de Barbastelle et
   600 de Pipistrelle commune peuvent tous deux être « Forte » — c'est normal.
   **Raisonnez espèce par espèce.**
2. **Une classe d'activité n'est pas un niveau d'enjeu.** Une activité « faible »
   ne veut pas dire un enjeu faible : une espèce rare et discrète reste un enjeu
   majeur. Activité et patrimonialité sont deux lectures distinctes.
3. **C'est une aide à l'interprétation**, valable si le protocole est respecté
   (matériel conforme, micro < 6 m, métropole, bonne saison) — pas un verdict.
   L'expertise du chiroptérologue reste souveraine.

> **Référentiel cité par ChiroTool** : Bas Y., Kerbiriou C., Roemer C. & Julien J.-F. (2020),
> *Bat reference scale of activity levels* (Team-Chiro / MNHN). Unité : contacts
> par nuit. Merci de citer cette source si vous reprenez ces niveaux dans un rapport.
> Ce n'est pas l'outil d'activité de ChiroSurf.

---

## 10 · Visualiser l'activité des espèces

L'onglet **« Activité »** transforme vos tableurs d'observations en **graphes
d'activité horaire** pour un rapport ou une analyse. Ces graphes sont ceux
de ChiroTool. Ils ne remplacent pas l'évaluation d'activité de ChiroSurf.

![Exemple de graphe d'activité](captures/exemple-graphe-activite.png)

*Exemple : activité de trois espèces sur une nuit, par tranche de 30 minutes.*

À gauche, un panneau de **filtres** permet de cibler précisément :

- **Sites** (carrés STOC) et **Points** (Z1, Z2…)
- **Passages** (Pass1, Pass2…)
- **Nuits** (une seule, ou plusieurs à cumuler)
- **Taxons** (espèces et groupes)
- **Chiros seulement** : masquer orthoptères, bruit, oiseaux
- **Taxons observateur** : ne garder que les lignes où vous avez renseigné
  l'espèce (ex. un Nyclas que Tadarida avait mis en Nycnoc).
- **Validés humains seulement** : lignes avec identification observateur ou
  validateur.
- **Interprétation _Vu (ChiroSurf)** : même relecture que la Synthèse
  (bandes de confiance Tadarida, `_Vu` nuit par nuit). Distinct de « validés
  humains ». Les deux cases s'excluent. Sans `_Vu`, un rappel s'affiche :
  la relecture vise un fichier produit dans ChiroSurf.
- Un `_Vu` dans `chirosurf/`, `Data_k/` **ou à la racine de la session**
  **remplace le tableur pour cette nuit seulement**. Les autres nuits de
  la participation restent lues dans l'xlsx. Cocher la relecture, chiros ou
  les taxons observateur ne relit pas le disque (cache mémoire). Les autres
  carrés restent dans la liste de filtres.

Chaque section se **replie** et affiche son état (`8 / 42`), pour garder le
panneau lisible même sur une grosse campagne. Les listes longues (nuits, taxons)
ont une **barre de recherche** : tapez `pip`, vous trouvez. Un bouton
**« Réinitialiser »** remet tout à zéro, et un résumé en haut rappelle les
filtres actifs.

Les filtres sont **en cascade** : choisir un site restreint les points
disponibles, puis les passages, puis les nuits.

Deux modes :

- **Cumulé** : une courbe par espèce, somme de tous les points/nuits sélectionnés.
- **« Détailler par point »** : une courbe par couple espèce × point — idéal pour
  comparer Z4 et Z5 d'un même carré sur la même nuit.

> 💡 La « nuit biologique » est gérée correctement : un contact à 2h du matin est
> rattaché à la nuit commencée la veille au soir.

Cliquez sur **« 💾 Exporter PNG »** pour obtenir une image propre du graphe
(titre, axes, légende inclus) à glisser dans vos rapports.

---

## 11 · Travailler en équipe

ChiroTool est pensé pour les structures où **plusieurs personnes** font du
terrain.

### Le Registre : votre suivi global

L'onglet **« Registre »** affiche **toutes vos nuits, toutes campagnes
confondues**, avec leur état d'avancement.

> 📸 **[Capture 13 — Onglet Registre, vue groupée par contrat]**

Vous pouvez :
- Filtrer par année, contrat, état, ou rechercher
- Éditer les commentaires (double-clic)
- **« 🔄 Sync API »** : se synchroniser avec Vigie-Chiro pour récupérer l'état des
  participations (et détecter les nuits faites par d'autres)
- **« 🧹 Doublons »** : nettoyer d'éventuelles entrées en double (après un
  changement de PC, par exemple)

### Partager le suivi : l'export CSV

Bouton **« 📤 Exporter »** → **CSV** : vous obtenez un fichier complet (38
colonnes) avec toutes vos nuits. Chaque membre de l'équipe peut exporter le sien,
et un responsable peut les fusionner pour avoir la **vue d'ensemble de la
campagne** (qui a fait quoi, où, combien de nuits restent).

Les autres formats du même menu (**Registre .db**, **Excel**) restent disponibles
pour sauvegarder ou croiser le suivi.

### Emporter des nuits sur une clé USB (sons traités + métadonnées)

Cas typique : vous voulez emmener **uniquement le Data_k** (WAV déjà en TE×10)
et les métadonnées sur une clé ou un disque, en laissant les **bruts Data/**
(lourds) sur le PC principal.

1. Onglet **Registre** → **« 📤 Exporter »** → **« 🌙 Sessions (USB) »**.
2. Cochez le(s) **contrat(s)** et les **nuits** voulues.
3. Options audio :
   - **Data_k (TE×10)** — coché par défaut (recommandé pour le partage) ;
   - **Data (bruts)** — décoché par défaut ;
   - les **métadonnées** (manifest, xlsx d'observations, Summary, etc.) sont
     **toujours** incluses ;
   - le dossier **`chirosurf/`** (CSV multi-nuits / `_Vu`) est emporté s’il
     existe, sans option à cocher.
4. Lisez l'**estimation de volume**, choisissez le dossier de destination
   (clé USB…), confirmez.
5. Un journal de copie s'affiche. À la fin, un dossier
   `ChiroTool_export_AAAAMMJJ_HHMMSS/` contient une arborescence **relative**
   rejouable. Sur l'autre poste : **Parcourir…** vers ce dossier (ou vers le
   dossier de campagne qu'il contient), puis **Scanner**. N'ouvrez pas un
   sous-dossier `Data_k/` : c'est le miroir TE, pas la session.

> 💡 Pour un partage « léger » : Data_k **oui**, Data **non**. Pour une archive
> complète de la nuit, cochez les deux. Pour une relecture pure synthèse /
> `_Vu` sans sons : Data_k **non**, Data **non** (meta + chirosurf seulement).

### Partager le matériel

Le parc d'enregistreurs peut être **exporté** (📤) et **importé** (📥) entre
postes, ou simplement déposé dans le dossier de travail commun pour un import
automatique.

### Créer un carré ou rejoindre celui d'un autre observateur

Depuis l'onglet **Carte**, cliquez sur **« ➕ Ajouter un point »** puis sur
l'emplacement voulu. ChiroTool identifie automatiquement le **carré** (cellule
de la grille nationale STOC 2×2 km) correspondant :

- **Le carré n'existe pas encore sur Vigie-Chiro ?** ChiroTool propose de le
  **créer** (vous en devenez le propriétaire). Plus besoin de passer par le
  portail web.
- **Le carré existe déjà, même créé par un autre observateur ?** Ses points
  s'affichent sur la carte (🟢 les vôtres, 🟠 ceux des autres) et dans
  l'assistant, triés du plus proche au plus loin. Vous pouvez **réutiliser un
  point existant** (recommandé s'il est au même endroit, pour la continuité du
  suivi) ou **créer votre propre point** sur ce carré.

Après create **ou** reuse, le point est mémorisé pour la **prochaine préparation**
(préremplissage carré + code point + GPS dans le manifest, y compris pour un
site d’un autre observateur). Même effet via le bouton vert de la fiche point :
**« ★ Utiliser pour la prochaine préparation »**.

> 💡 Rejoindre le carré d'un autre observateur ne change pas sa propriété :
> chacun reste **propriétaire de ses nuits** (participations). Les points déjà
> en place ne sont jamais modifiés ni écrasés.

> ⚠ La création d'un carré est **définitive** (seul un administrateur
> Vigie-Chiro peut le supprimer) : vérifiez l'emplacement avant de confirmer.

> 🔎 **Deux usages carte** :
> - **📍 Voir sur la carte** (depuis une nuit) → zoom + pin rose sur ce point ;
> - **🔄 Recharger sites** / **Mes sites** / **France** → tous vos sites,
>   vue d’ensemble (sort du mode FOCUS).
>
> Utilisez la **recherche de lieu / commune** pour zoomer avant d’ajouter un
> point.

---

## 12 · Questions fréquentes & dépannage

**« L'application affiche un avertissement Windows au lancement. »**
C'est normal (logiciel libre non signé). Cliquez sur « Informations
complémentaires » → « Exécuter quand même ».

**« Mon token ne fonctionne plus. »**
Il a probablement expiré (~30 jours). Refaites la procédure F12 (Préférences →
API Vigie-Chiro).

**« La préparation s'arrête avec une erreur de fichiers en double. »**
Certains enregistreurs produisent occasionnellement des fichiers mal nommés ou en
double. Vérifiez le dossier `Data/` et retirez les fichiers manifestement
corrompus, puis relancez.

**« L'application se ferme toute seule pendant la préparation. »**
Certains antivirus d'entreprise (Trend Micro, etc.) coupent l'application quand
elle crée beaucoup de fichiers d'un coup (renommage/expansion), qu'ils prennent
à tort pour un rançongiciel. Deux solutions :
- **Placez votre dossier de travail hors du Bureau / Documents / Images** (ces
  dossiers sont « protégés » par défaut) — par exemple `C:\ChiroData\`.
- Activez **Préférences → Général → Mode compatible antivirus** : le renommage
  est alors *lissé* (plus lent, mais passe souvent sous le radar de l'antivirus).
- En dernier recours, demandez à votre service informatique d'**autoriser
  `ChiroTool.exe`** dans l'antivirus.
Aucune donnée n'est perdue : relancer la préparation reprend là où elle s'était
arrêtée.

**« Au lancement, le logiciel ne répond pas / Parcourir est grisé. »**
ChiroTool **n'ouvre plus** tout seul le dernier dossier : un SSD EXFAT
endormi ou un gros scan bloquait l'interface et grisait Parcourir.
**Parcourir reste cliquable** pendant un scan. Si **Préférences → Général →
Garder en mémoire le dernier dossier** est coché (défaut), le chemin
reste affiché : **Parcourir** pour un autre dossier, **Scanner** pour
recharger celui-ci. Décochez pour partir de `(aucun)` au prochain lancement.

**« Mes fichiers Anabat Swift / Ranger ne sont pas reconnus. »**
Les noms usine `YYYY-MM-DD HH-MM-SS.wav` (espace ou underscore, éventuellement
précédés du n° d'enregistreur) sont lus. Un WAV plus long que 5 s est découpé
en tranches horodatées (tout le son est conservé). Si **Préparer s'arrête**
faute de nom lisible, passez une fois par XnView vers `YYYYMMDD_HHMMSS.wav`
et joignez un exemple de nom à une [issue](https://github.com/kevin-guille/ChiroTool/issues).

**« Avec la 0.7.2, seuls les 5 premières secondes des Anabat longs partent. »**
Oui : le moteur TE×10 (Rust) réutilisait le même nom pour chaque tranche
d'un WAV de plus de 5 s. Seule la première était gardée. C'est corrigé
dans la **v0.8.0** (et les suivantes). **Ne pas uploader** ce `Data_k`. Installez l'exe **0.8.1**,
relancez **▶ Préparer** : les fichiers déjà écrits restent, les
tranches manquantes s'ajoutent. Dans l'Historique, une ligne du type
`402 sources → 470 segments · 402 écrits` signale le trou. Tant que
Préparer n'a pas rattrapé, **Upload** reste grisé.

**« Mes fichiers SM2 sont en .WAC (ou .w4v). »**
ChiroTool **ne décompresse pas** les formats Wildlife **`.wac`** (SM2, parfois
SM3) et **`.w4v`**. Un `.wac` SM2 peut coller **toute une heure de triggers**
dans un seul fichier : le traiter tel quel produirait des milliers de tranches
de 5 s vides. Convertissez **avant** Préparer, sur une **copie** (gardez les
WAC d'archive) — même logique que l'AudioMoth `T.WAV` à expander.

1. **Kaleidoscope Lite** (conversion batch **sans licence Pro**) ou l'ancien
   **WAC2WAV** avec **Split Triggers**.
2. Entrée **WAC** (ou W4V) ; sortie **WAV** uniquement (pas W4V, pas ZC).
3. Expansion temporelle de **sortie = 1** (le TE×10, c'est ChiroTool).
4. **Disable noise filtering** (consigne Vigie-Chiro : oreillard, natterer,
   barbastelle).
5. Stéréo : séparez les canaux et ne gardez que le micro chauves-souris.

Contrôle : beaucoup de **courts** WAV `PREFIX_YYYYMMDD_HHMMSS.wav` (un suffixe
`_mmm` est possible). Un WAV énorme par WAC = les triggers n'ont pas été
extraits (WAC2WAV + Split Triggers, ou « split max duration » 5 s dans
Kaleidoscope). Noms à corriger (XnView / Lupas) s'ils cassent le renommage :
canal `_0_`, tag `_T_`, préfixe `NOISE_`, espaces.

Déposez ensuite ce dossier de WAV dans ChiroTool et lancez **Préparer**
(rename + TE×10 + tranches 5 s) comme une nuit SM4. Le SM2 n'écrit pas de
`Summary.txt` SM4 : dates d'après les noms de fichiers, météo à la main dans
l'assistant.

Si l'appareil enregistre déjà en **WAV trigger**, sautez Kaleidoscope.
Si Kaleidoscope a **déjà** fait le TE×10, ne le refaites pas : ChiroTool
détecte un sample rate ≤ 60 kHz et/ou un suffixe `_000` et considère le TE
fait (rename + upload seulement).

**« L'upload refuse, ou les dates de participation sont fausses. »**
Si le `Summary.txt` ne correspond pas aux WAV du dossier, ChiroTool **prévient
dès la préparation** et **avant l'upload**. Les fichiers WAV font foi.
Cause fréquente : carte SD **non formatée** entre deux nuits — le Summary
garde l'ancienne pose et y ajoute la nouvelle. Les dates (et, si possible,
les T°) sont prises sur la fenêtre des WAV. Une participation déjà créée au
mauvais jour n'est plus réutilisée.

**« La préparation est très lente, ou plante, sur un SSD externe. »**
Sous Windows, un disque (surtout externe) formaté en **EXFAT** tient très mal
le renommage / TE×10 sur des milliers de WAV : fortes lenteurs, parfois un
plantage. Ce n'est pas propre à ChiroTool (même constat avec Lupas Rename ou
Kaleidoscope). Contournements :

1. **Copier le dossier de nuit sur le disque local (NTFS)** avant de lancer
   la préparation : c'est le geste le plus simple.
2. Si vous le pouvez, formater le SSD en **NTFS** (sauvegarde d'abord). Ce
   n'est pas obligatoire.
3. Activer le **Mode compatible antivirus** dans les Préférences (ça lisse
   le renommage ; ça n'annule pas le handicap EXFAT).

Le NTFS est fortement recommandé pour les campagnes de plus de quelques
centaines de WAV. Sinon on peut croire à tort que le logiciel est trop lent.

**« L'upload s'est interrompu (PC éteint, coupure réseau). »**
La nuit s'affiche en orange ⏳ « à reprendre ». Re-cliquez **Upload + Tadarida** :
les fichiers manquants sont renvoyés, ceux **déjà enregistrés** (code 409) sont
sautés, puis Tadarida peut partir. Si l'app affiche encore des échecs ou refuse
de lancer l'analyse : **🔧 Vérifier / Réparer**. Si Tadarida sort **0 contact**
alors que la nuit n'était pas silencieuse, le son n'est pas sur le serveur :
nouvelle participation et renvoyer `Data_k/`.

**« Vérifier / Réparer dit que le listing a échoué, mais propose Tadarida. »**
C'est voulu. Le portail n'arrive parfois pas à *lister* les fichiers (erreur
403), alors que les noms sont déjà enregistrés (code 409). ChiroTool le
vérifie, puis vous laisse lancer l'analyse. Copiez le rapport dans une
[issue GitHub](https://github.com/kevin-guille/ChiroTool/issues) si besoin.

**« Je ne peux pas cliquer sur "Nettoyer". »**
Le bouton est grisé tant que le tableur d'observations n'a pas été récupéré
(étape Upload + Tadarida). C'est normal.

**« 📍 Carte ne trouve pas mon point. »**
Le recentrage utilise d’abord les **GPS du manifest**, puis le point actif, puis
le cache API. Si rien n’est connu : message orange (plus de zoom France
trompeur). Solution : une fois **🗺️ Choisir sur la carte…** ou create/reuse.
Pour revoir **tous** les sites après un FOCUS : **🔄 Recharger sites**.

**« Après un export USB, rien ne s'affiche (Excel présents) et Vérifier / Réparer dit *pas d'ID participation*. »**
Le scan prenait `Data_k/` pour la session : le tableur, le Summary et le
manifest sont dans le dossier **parent**. Mettez à jour ChiroTool (**0.8.1**
ou plus), ouvrez `ChiroTool_export_…` (pas `Data_k`), puis **Scanner**.
Ce n'est pas la peine de relancer l'analyse : les fichiers y sont déjà.

**« Après un export ou un nettoyage, la pastille reste jaune et Préparer ressort, alors que Vérifier / Réparer dit que tout est bon. »**
Les WAV bruts (souvent 384 kHz) sont encore dans le dossier, et `Data_k/`
a été purgé. L'ancien contrôle Titley prenait ce sous-ensemble pour un
TE×10 incomplet. À partir de **0.8.1**, si `_stats_before_cleanup.json`
est là, TE×10 reste coché et la pastille passe au vert. **Scanner**
suffit, sans relancer Préparer.

**« Vérifier / Réparer propose de tout re-uploader. »**
Vérifiez d'abord le **token** (401 = expiré → Préférences → API). Avec un bon
token, le rapport distingue : couverture 100 % des locaux restants, fichiers
« sur serveur seul » après nettoyage, vrais manquants dans Data_k, ou fichiers
déjà enregistrés (code 409, pas un re-upload). Le journal complet peut être
collé dans une [issue GitHub](https://github.com/kevin-guille/ChiroTool/issues).

**« Comment préparer une participation multi-nuits pour ChiroSurf ? »**
La validation se fait dans ChiroSurf. **🌊 ChiroSurf nuits** → **Ouvrir dans
ChiroSurf** sur le CSV brut (sans `_Vu`) → le `_Vu` apparaît à côté →
**📈 _Vu** pour rouvrir ce fichier. La Synthèse ChiroTool peut ensuite le
relire. Voir [§8 B](#b--préparer-un-csv-par-nuit-pour-chirosurf-optionnel).

**« ChiroSurf s'ouvre puis affiche *Error in startup script* / *no files matched glob pattern*. »**
ChiroSurf 4.x cherche les WAV **dans le dossier du CSV**. La v0.7.1 copie
le CSV dans `Data_k/` avant l'ouverture. Si le message persiste : (1) le
chemin ChiroSurf.exe est bien 4.6+ ; (2) `Data_k/` contient encore des
`.wav` (une nuit déjà nettoyée n'a plus de sons). Voir [§8 B](#b--préparer-un-csv-par-nuit-pour-chirosurf-optionnel).

**« J'ai collé un `_Vu` dans chirosurf/ et ChiroTool ne le voit pas. »**
Les noms `Nuit1_…_Vu.csv` **et** `Nuit_1-…_Vu.csv` (nomenclature manuelle /
issue #3) sont lus, y compris un `_Vu` laissé dans `Data_k/` ou **à la
racine de la session**. Fermez et rouvrez **🌊 ChiroSurf nuits**,
**📊 Synthèse** ou **⟳ Recharger** dans l'onglet Activité. Voir [§8 B](#b--préparer-un-csv-par-nuit-pour-chirosurf-optionnel).

**« L'assistant « Nouvelle participation » s'ouvre tout noir, l'upload unitaire ne part pas. »**
Corrigé en **0.8.1** (issue #9). Le formulaire s'affiche d'abord ; le
log Titley / Summary se lit ensuite. Le **batch** n'ouvre pas cet assistant
(d'où l'impression que « seul le batch marche »). Mettez à jour l'exe.

**« En batch Préparer, les dernières nuits disent OK mais les fichiers n'ont pas été renommés. »**
Le batch ignore une nuit dont le carré / point n'est pas connu (pas
d'assistant). En **0.8.1** cette ignorance pouvait compter comme un succès.
Préparez d'abord ces nuits **une par une**, puis le batch. Voir [§7](#7--traiter-plusieurs-nuits-dun-coup-mode-batch).

**« L'onglet Activité est très lent, les filtres ne font rien, un seul carré s'affiche. »**
Corrigé en **0.8.1** (issue #10). Les tableurs sont gardés en mémoire :
cocher la relecture _Vu ou « chiros seulement » ne relit plus le disque.
Tous les carrés restent dans la liste. **⟳ Recharger** relit les fichiers.
La Synthèse, elle, lisait déjà le `_Vu` de la session ouverte.

**« La Synthèse me propose Nuit 1 et Nuit 2 pour une pose d'un soir. »**
Ce n'est plus le cas depuis la **v0.7.2**. Une pose 21 h → 6 h = **une**
nuit (coupure à **midi**, pas à minuit). Le menu Nuit n'apparaît que s'il y
a **deux soirs**. Si vous voyez encore deux nuits : des fichiers sont
horodatés **après midi** le lendemain (deuxième soirée réelle, ou carte SD
non formatée). Voir [§8 — Règle de la nuit](#règle-de-la-nuit-ne-plus-la-recasser).

**« ChiroSurf nuits affiche 2 lignes alors que je n'ai posé qu'une nuit. »**
Même règle : le matin du 17 reste la nuit du 16. Deux lignes = fichiers
**≥ 12 h le second jour**. Vérifiez les heures dans `nom du fichier` :
Nuit 2 à 21 h = deux soirs ; Nuit 2 à 02 h = anomalie à signaler.
Le dossier `20260716_site…` ne dit pas « une seule nuit ».
Voir [§8](#règle-de-la-nuit-ne-plus-la-recasser).

**« Je ne vois pas Synthèse / ChiroSurf nuits, seulement jusqu'à Carte. »**
Glissez la barre d'actions vers la **droite** (molette sur la ligne, ou le
curseur sous les boutons). Dans la fenêtre ChiroSurf nuits, ▶ / 📈 / Synthèse
sont **sous** le nom de la nuit.

**« Où est la relecture d'un fichier _Vu ? »**
Case **« Interprétation _Vu (ChiroSurf) »** dans **📊 Synthèse** et dans
l'onglet **Activité**, distincte de **« Identifications validées seulement »**
(lignes écoutées). Elle relit un `_Vu` déjà produit dans ChiroSurf. Elle
n'applique pas la procédure de validation Vigie-Chiro. Voir
[§8 B](#b--préparer-un-csv-par-nuit-pour-chirosurf-optionnel) et l'issue
[#7](https://github.com/kevin-guille/ChiroTool/issues/7).

**« Où sont stockées mes données ? »**
Votre index et vos sauvegardes sont dans le sous-dossier `_chirotool/` de votre
dossier de travail. Un fichier `README.txt` y explique chaque fichier. **Ne le
supprimez pas** (sinon ChiroTool devra tout re-scanner).

**« Après Afficher le bureau, je ne retrouve plus la fenêtre ChiroTool. »**
Cliquez l'icône ChiroTool dans la barre des tâches, ou celle de la fenêtre
de progression (Préparer, Upload, etc.). Elle revient au premier plan.
Inutile de tuer le process dans le Gestionnaire des tâches.

**« L'application s'est fermée toute seule. »**
Un fichier de journal est créé dans `%APPDATA%\ChiroTool\chirotool.log`.
Envoyez-le à votre référent ou via la page Issues du projet, cela aide à
diagnostiquer.

---

## 13 · Limites connues

ChiroTool couvre la grande majorité des cas, mais pas (encore) tout :

- **Enregistreurs compatibles** : Wildlife (SM2/3/4/Mini Bat), Passive Recorder,
  Bat Recorder, **AudioMoth** (fichiers *expandés*) et **Titley** Anabat Swift /
  Ranger (`YYYY-MM-DD HH-MM-SS`, WAV > 5 s découpés en entier, voir
  [§12](#12--questions-fréquentes--dépannage)).
  Les AudioMoth bruts `…HHMMSS**T**.WAV` doivent d'abord être expandés
  (Configuration App → *Expand*). Les noms **non datés** (Peersonic,
  Pettersson D500x) nécessitent un renommage préalable (XnView vers
  `YYYYMMDD_HHMMSS.wav`). Si **aucun** nom n'est lisible, Préparer s'arrête.
- **Fichiers compressés `.wac` / `.w4v`** : non décompressés. Convertissez
  d'abord en WAV horodatés (Kaleidoscope Lite, expansion de sortie **×1**,
  sans filtre bruit, **un fichier par trigger**), puis Préparer. Détail
  [§12](#12--questions-fréquentes--dépannage) (« Mes fichiers SM2 sont en
  .WAC »).
- **Modifier une participation déjà créée** (météo erronée…) : via le portail web.
- **Supprimer un carré créé par erreur** : action réservée aux administrateurs
  Vigie-Chiro (contactez l'équipe du programme).
- **Participation multi-nuits** : **📊 Synthèse** n'affiche le menu Nuit
  que s'il y a **plusieurs soirs** (une pose qui passe minuit = une nuit).
  **🌊 ChiroSurf nuits** prépare un CSV pour l'ouvrir dans ChiroSurf
  (voir [§8](#règle-de-la-nuit-ne-plus-la-recasser)). La validation
  Vigie-Chiro se fait dans ChiroSurf. La Synthèse et l'onglet Activité
  peuvent relire le `_Vu` avec **« Interprétation _Vu (ChiroSurf) »**.
  La validation contact par contact dans ChiroTool reste disponible, et
  elle est distincte de la procédure ChiroSurf.
- **Bouton 📍 Carte** : si les GPS n’ont jamais été mémorisés pour la session,
  choisissez une fois le point (pick carte ou create/reuse) pour les enregistrer.
- **SSD / disques EXFAT sous Windows** : le renommage et le TE×10 y sont
  souvent lents ou instables. Copier la nuit sur un volume NTFS (disque local)
  avant de préparer ; voir [§12](#12--questions-fréquentes--dépannage).

---

## 14 · Nouveautés v0.8 / v0.7

| Zone | Ce qui change |
|------|----------------|
| **Synthèse** | **v0.8.0** : case **Interprétation _Vu (ChiroSurf)** (relecture d'un fichier produit dans ChiroSurf, colonne Seuil _Vu, issue #7). `_Vu` lu s'il existe. Menu Nuit **seulement** s'il y a plusieurs soirs (v0.7.2 : une pose minuit = 1 nuit) |
| **Activité** | Un `_Vu` remplace le tableur **pour cette nuit seulement** (`chirosurf/`, `Data_k/`, racine de session). Même case de relecture que la Synthèse. **v0.8.1** : cache mémoire, plus de rescan à chaque case, les autres carrés restent dans les filtres |
| **ChiroSurf nuits** | Optionnel : CSV pour ouvrir la nuit dans ChiroSurf. La validation se fait dans ChiroSurf, pas dans ChiroTool. Coupure **midi**. **v0.7.1** : CSV à côté des WAV ; `_Vu` `Nuit_1_…`. **v0.7.2** : boutons sous le libellé (écran classique) |
| **Barre d'actions** | **v0.7.2** : une ligne, glissement horizontal si l'écran est étroit |
| **Valider** | Tri des colonnes, filtres observateur / chiros, bilan `X / Y` (issue #4) |
| **Valider / Nettoyer** | **Nettoyer** à droite de **Valider** (on identifie, puis on purge) |
| **Batch** | Plusieurs nuits dans **une** instance (case ☐ Batch). Pas plusieurs exe. |
| **Titley** | Swift / Ranger : noms usine lus ; un WAV > 5 s est découpé **en entier** (plus seulement les 5 premières secondes, issue #4) |
| **Démarrage** | Plus de scan auto du dernier dossier (issue #5) |
| **Upload / Réparer** | Coupure réseau : code 409 = déjà enregistré, Tadarida peut partir. **Vérifier / Réparer** lance l'analyse si le listing portail échoue ; 0 contact → renvoyer Data_k. **v0.8.1** : wizard d'upload visible tout de suite (issue #9) ; fermer la fenêtre = arrière-plan, recliquer Upload la rouvre |
| **Participation Titley** | **v0.8.1** (issue #8) : n° de série, type, micro, horaires et T° du `log_*.csv` envoyés à Vigie-Chiro |
| **Export USB** | **v0.8.1** : un scan d'un paquet Data_k-only retrouve la session (plus le dossier `Data_k/` lui-même). Excel, Summary et ID participation réapparaissent. Ouvrir `ChiroTool_export_…`, pas `Data_k` |
| **Pastille / TE×10** | **v0.8.1** : après nettoyage, Data_k plus petit que les bruts ne recule plus TE×10 (pastille verte, plus de Préparer en faux « next ») |
| **Fenêtres** | Après **Afficher le bureau** (Win+D), recliquer ChiroTool ramène la progression. Plus besoin de tuer le process |
| **Dates** | WAV font foi si Summary cumulé |
| **SM2** | `.wac` / `.w4v` : conversion Kaleidoscope Lite en amont (issue #6) |

La **v0.6** (carte pick/FOCUS, Vérifier / Réparer, export USB, météo non
bloquante, CSV ChiroSurf) reste le socle — voir le
[changelog](https://github.com/kevin-guille/ChiroTool/blob/main/CHANGELOG.md).

Conception / dev : [`SPEC_v06_parcours.md`](SPEC_v06_parcours.md) · issues
[#3](https://github.com/kevin-guille/ChiroTool/issues/3),
[#4](https://github.com/kevin-guille/ChiroTool/issues/4),
[#5](https://github.com/kevin-guille/ChiroTool/issues/5),
[#6](https://github.com/kevin-guille/ChiroTool/issues/6),
[#7](https://github.com/kevin-guille/ChiroTool/issues/7),
[#8](https://github.com/kevin-guille/ChiroTool/issues/8),
[#9](https://github.com/kevin-guille/ChiroTool/issues/9),
[#10](https://github.com/kevin-guille/ChiroTool/issues/10),
[#11](https://github.com/kevin-guille/ChiroTool/issues/11).

### Suite (hors 0.8.1)

Ne pas relire le 1er message des issues
[#4](https://github.com/kevin-guille/ChiroTool/issues/4),
[#7](https://github.com/kevin-guille/ChiroTool/issues/7),
[#8](https://github.com/kevin-guille/ChiroTool/issues/8),
[#9](https://github.com/kevin-guille/ChiroTool/issues/9) et
[#10](https://github.com/kevin-guille/ChiroTool/issues/10) comme une todo
(SPEC §0.1 à §0.4). Issue
[#11](https://github.com/kevin-guille/ChiroTool/issues/11) : réouverture
du suivi livrée ; fermeture de l'exe et historique live restent ouverts
(SPEC §0.5).

- Robustesse / UX du **mode batch**, journal d'upload (issue #11).
- **Batch Préparer** (interne, SPEC §0.6, pas d'issue GitHub) : dernières
  nuits d'une série (~15) parfois sans renommage alors que le bilan disait
  OK. Cible 0.8.2. En 0.8.1 : préparer ces nuits **une par une**, puis le
  batch.
- Export compilé espèces × nuits ; fusion `_Vu` → xlsx (choix produit).
- Pas plusieurs exe : le Batch enchaîne les nuits (SPEC D14).

---

## 15 · Crédits & licence

**ChiroTool** est un projet **libre et open-source**.

- **Auteur** : Kevin Guille
  [LinkedIn](https://fr.linkedin.com/in/kevin-guille-764b6a150)
- **Projet** : personnel, développé sur temps personnel
- **Protocole & API** : [Vigie-Chiro / MNHN](https://www.vigienature.fr/fr/chauves-souris)
- **Licence** : MIT (usage et contributions libres)

> 🐙 Code source, bugs et contributions : [github.com/kevin-guille/ChiroTool](https://github.com/kevin-guille/ChiroTool)

---

<div align="center">

*Vous avez des retours, des bugs, des idées ? N'hésitez pas à les remonter.*
*ChiroTool grandit grâce aux utilisateurs de terrain.*

**Bon traitement, et bonnes chauves-souris ! 🦇**

</div>
