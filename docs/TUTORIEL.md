<div align="center">

# 🦇 ChiroTool

### Le traitement de vos nuits chiroptères, automatisé de A à Z

*Outil libre pour le protocole **Vigie-Chiro Point Fixe** (MNHN)*

![Icône ChiroTool](captures/icon_256.png)

**Version 0.6** · Tutoriel utilisateur

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
14. [Nouveautés v0.6](#14--nouveautés-v06-issue-3--suite)
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

1. Récupérez le fichier **`ChiroTool.exe`** (≈ 34 Mo) auprès de votre référent ou
   sur la page de téléchargement officielle.
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
- **Activité** : graphes par tranche horaire ; filtres **Chiros seulement** et
  **Taxons observateur** (y compris les `_Vu` ChiroSurf)

### La barre d'actions

En bas de la **Vue session**, une barre unique regroupe tout ce que vous pouvez
faire sur la nuit sélectionnée :

> **▶ Préparer** · **☁ Upload** · **🔧 Vérifier / Réparer** · **🔍 Valider** ·
> **🧹 Nettoyer** · **🌊 ChiroSurf nuits** · **✎ Métadonnées** · **📍 Carte** ·
> **📊 Synthèse** · **⋯ Détails**

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
   Kaleidoscope. Un WAV déjà en 5 s reste un fichier ; un WAV plus long sort
   en plusieurs WAV (nouveau timestamp toutes les 5 s). **Tout le son est
   conservé**, ce n'est pas un prélèvement des 5 premières secondes. Le
   protocole Point Fixe règle en général les SM4 sur 5 s : dans ce cas le
   nombre de fichiers ne change pas.

Une **barre de progression** vous indique l'avancement en temps réel.

> 📸 **[Capture 08 — Fenêtre de progression avec la barre et l'ETA]**

### Étape 3 — Upload + Tadarida

Cliquez sur **« ▶ Upload + Tadarida »**.

Un **assistant de participation** s'ouvre. Il pré-remplit ce qu'il **sait
réellement** : les T° si votre `Summary.txt` les contient, le matériel depuis
votre parc, les dates du Summary **si c'est une seule nuit**. Si le Summary
ne correspond pas aux WAV, un **avertissement** le dit : dates (et T° sur
la fenêtre des fichiers) prises sur les WAV. Vous pouvez encore corriger ;
une participation déjà créée au mauvais jour n'est pas réutilisée.

> 📸 **[Capture 09 — Assistant « Nouvelle participation Vigie-Chiro »]**

- **Conditions météo** (optionnel) : températures (souvent issues du
  `Summary.txt`), vent, couverture nuageuse
- **Matériel** : détecteur, micro, hauteur
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
2. **Attente Tadarida** — l'analyse tourne **sur les serveurs Vigie-Chiro**.
   Cela peut prendre de quelques minutes à quelques heures. **Vous pouvez fermer
   l'application** : cliquez sur **« 🔌 Arrière-plan »**, l'analyse continue
   côté serveur sans vous.
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
   - **relancer Tadarida** (double confirmation — uniquement si la couverture est
     complète et que le compute n'est pas déjà en cours / terminé).
5. Si des WAV **encore présents dans Data_k** manquent vraiment sur le serveur,
   l'outil propose de reprendre via **« ☁ Upload »**.

> 💡 **Après nettoyage** : des fichiers peuvent rester « sur le serveur seulement »
> (ex. 185 purgés localement). C'est **normal** — seuls les WAV encore dans
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

Vous avez 10 nuits à traiter ? Pas besoin de les faire une par une.

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

---

## 8 · Valider les sons et remonter vos identifications

L'identification de Tadarida est automatique : pour fiabiliser vos données, vous
pouvez valider **de deux façons** (complémentaires, pas exclusives).

### A · Validation contact par contact (ChiroTool)

1. Sur une nuit dont le tableur est récupéré, cliquez sur **« 🔍 Valider »**.
2. Un tableau filtrable des contacts s'affiche :
   - **Clic sur un en-tête** pour trier (A–Z ou petit–grand). Un 2e clic inverse ;
     un 3e revient à l'ordre d'origine. Pratique pour ramener en haut les plus
     fortes probas d'une espèce.
   - **« Taxon observateur renseigné uniquement »** : n'afficher que les lignes
     déjà validées (à la place de « Non validés seulement », les deux cases ne
     se cumulent pas).
   - **« Chiros seulement »** : masquer orthoptères, bruit, oiseaux.
   - **CSV nuits** : ouvre la liste des CSV ChiroSurf (même fenêtre que
     **🌊 ChiroSurf nuits**).
3. Sélectionnez un contact, puis :
   - Utilisez les **raccourcis clavier** `O` / `P` / `S` pour indiquer votre
     niveau de confiance (pOssible / Probable / Sûr).
   - **Double-cliquez** (ou **▶ ChiroSurf**) pour ouvrir le WAV dans
     **ChiroSurf** (chemin dans Préférences → Outils).
4. Vos validations sont sauvegardées dans un nouveau tableur suffixé de vos
   initiales (ex : `…_AB.xlsx`). Un bandeau **« ● modifications non
   enregistrées »** (titre + bouton *Enregistrer* orangé) vous rappelle de
   sauvegarder ; il disparaît après enregistrement.

> 📸 **[Capture 14 — Vue de validation : la saisie guidée (✓ connu), le bouton
> « Monter au genre » pour les sons incertains, et « Envoyer » qui remonte vos
> identifications vers Vigie-Chiro.]**

### B · Méthode MNHN / Team Chiro via ChiroSurf (10 % → 75 %)

Si votre **participation couvre plusieurs nuits** d’affilée (un seul tableur
Tadarida multi-nuits), le référentiel d’activité et la validation « optimisée »
ChiroSurf se basent sur une **nuit unique**. ChiroTool scinde pour vous :

1. Cliquez sur **« 🌊 ChiroSurf nuits »** (visible dès qu’un xlsx d’observations
   est présent ; aussi depuis **🔍 Valider** → **CSV nuits**).
2. ChiroTool crée le dossier `chirosurf/` dans la session et un CSV **par nuit
   biologique** (coupure à **midi**) :
   `Nuit1_<nom-du-tableur>-observations.csv`, `Nuit2_…`, etc.
3. **▶ ChiroSurf** ouvre le CSV **brut** (sans `_Vu`) — méthode 10 % → 75 %.
   Les WAV restent dans `Data_k/` de la session.
4. Après validation ChiroSurf, le fichier `…_Vu.csv` apparaît **à côté** du
   brut. **📈 _Vu** l'ouvre pour les **graphes** ChiroSurf. Pour poursuivre une
   validation, rouvrez toujours le CSV **sans** `_Vu`.
5. **Synthèse** sur une ligne de nuit lit le `_Vu` s'il existe. Cases
   **« identifications validées seulement »** (ne compte que `observateur_taxon`)
   et **« Chiros seulement »**. Avec la méthode 10 % → 75 %, ChiroSurf n'inscrit
   en observateur que les contacts **vraiment écoutés**, pas le reste de la nuit.

> ⚠️ Les CSV bruts peuvent être **régénérés** (bouton dans la fenêtre) ; les
> `_Vu` ne sont **jamais** écrasés automatiquement.

> 💡 La validation contact par contact (**🔍 Valider**) reste disponible en
> parallèle sur le tableur complet.

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
récapitulatif par espèce : combien de contacts, combien de fichiers, et surtout
**quel niveau d'activité**.

> 📸 **[Capture 15 — Synthèse d'une nuit : le niveau d'activité par espèce
> (colonne de droite) et le sélecteur « Milieu » qui affine le référentiel.]**

### Ce que vous lisez

En haut : **« X contacts détectés · Y identifiés (validés) · Z espèces de chiros »**,
plus la **source** (nom du xlsx, ou `_Vu nuit N` si vous venez de ChiroSurf nuits).

Filtres utiles :

- **« Identifications validées seulement »** : ne compter que les lignes où
  **taxon observateur** est renseigné (ignore Tadarida seul). Après un `_Vu`
  ChiroSurf 10 % → 75 %, ce sont les contacts écoutés, pas toute l'activité
  statistiquement retenue.
- **« Chiros seulement »** : masquer orthoptères, bruit, oiseaux.
- **« Proba Tadarida ≥ »** : seuil optionnel (ex. `0.5` ou `50`) pour la synthèse
  **non validée** ; les lignes déjà validées par l'observateur passent toujours.

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

> **Référentiel** : Bas Y., Kerbiriou C., Roemer C. & Julien J.-F. (2020),
> *Bat reference scale of activity levels* (Team-Chiro / MNHN). Unité : contacts
> par nuit. Merci de citer cette source si vous reprenez ces niveaux dans un rapport.

---

## 10 · Visualiser l'activité des espèces

L'onglet **« Activité »** transforme vos tableurs d'observations en **graphes
d'activité horaire** — parfait pour un rapport ou une analyse.

![Exemple de graphe d'activité](captures/exemple-graphe-activite.png)

*Exemple : activité de trois espèces sur une nuit, par tranche de 30 minutes.*

À gauche, un panneau de **filtres** permet de cibler précisément :

- **Sites** (carrés STOC) et **Points** (Z1, Z2…)
- **Passages** (Pass1, Pass2…)
- **Nuits** (une seule, ou plusieurs à cumuler)
- **Taxons** (espèces et groupes)
- **Chiros seulement** : masquer orthoptères, bruit, oiseaux
- **Taxons observateur** : ne garder que les lignes où vous avez renseigné
  l'espèce (ex. un Nyclas que Tadarida avait mis en Nycnoc). Si un dossier
  `chirosurf/` contient des `_Vu`, ce sont eux qui sont lus (pas le xlsx brut).

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
   rejouable : un scan ChiroTool sur l'autre poste retrouve les pastilles d'état.

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
Aucun problème : la nuit s'affiche en orange ⏳ « à reprendre ». Re-cliquez
« Upload + Tadarida » : seuls les fichiers manquants seront renvoyés.

**« Je ne peux pas cliquer sur "Nettoyer". »**
Le bouton est grisé tant que le tableur d'observations n'a pas été récupéré
(étape Upload + Tadarida). C'est normal.

**« 📍 Carte ne trouve pas mon point. »**
Le recentrage utilise d’abord les **GPS du manifest**, puis le point actif, puis
le cache API. Si rien n’est connu : message orange (plus de zoom France
trompeur). Solution : une fois **🗺️ Choisir sur la carte…** ou create/reuse.
Pour revoir **tous** les sites après un FOCUS : **🔄 Recharger sites**.

**« Vérifier / Réparer propose de tout re-uploader. »**
Vérifiez d’abord le **token** (401 = expiré → Préférences → API). Avec un bon
token, le rapport doit distinguer : couverture 100 % des locaux restants,
fichiers « sur serveur seul » après nettoyage, ou vrais manquants dans Data_k.
Le journal complet peut être collé dans une [issue GitHub](https://github.com/kevin-guille/ChiroTool/issues).

**« Comment valider une participation multi-nuits dans ChiroSurf ? »**
**🌊 ChiroSurf nuits** → **▶ ChiroSurf** sur le CSV brut (sans `_Vu`) → le `_Vu`
apparaît à côté → **📈 _Vu** pour les graphes, **Synthèse** dans ChiroTool.
Voir [§8 B](#b--méthode-mnhn--team-chiro-via-chirosurf-10--75-).

**« Où sont stockées mes données ? »**
Votre index et vos sauvegardes sont dans le sous-dossier `_chirotool/` de votre
dossier de travail. Un fichier `README.txt` y explique chaque fichier. **Ne le
supprimez pas** (sinon ChiroTool devra tout re-scanner).

**« L'application s'est fermée toute seule. »**
Un fichier de journal est créé dans `%APPDATA%\ChiroTool\chirotool.log`.
Envoyez-le à votre référent ou via la page Issues du projet, cela aide à
diagnostiquer.

---

## 13 · Limites connues

ChiroTool couvre la grande majorité des cas, mais pas (encore) tout :

- **Enregistreurs compatibles** : Wildlife (SM2/3/4/Mini Bat), Passive Recorder,
  Bat Recorder, **AudioMoth** (fichiers *expandés*) et **Titley** Anabat Swift /
  Ranger (`YYYY-MM-DD HH-MM-SS`, voir [§12](#12--questions-fréquentes--dépannage)).
  Les AudioMoth bruts `…HHMMSS**T**.WAV` doivent d'abord être expandés
  (Configuration App → *Expand*). Les noms **non datés** (Peersonic,
  Pettersson D500x) nécessitent un renommage préalable (XnView vers
  `YYYYMMDD_HHMMSS.wav`). Si **aucun** nom n'est lisible, Préparer s'arrête.
- **Fichiers compressés `.w4v` / `.wac`** : non décompressés (utilisez Kaleidoscope
  en amont).
- **Modifier une participation déjà créée** (météo erronée…) : via le portail web.
- **Supprimer un carré créé par erreur** : action réservée aux administrateurs
  Vigie-Chiro (contactez l'équipe du programme).
- **Participation multi-nuits** : utilisez **🌊 ChiroSurf nuits** pour scinder
  automatiquement (voir [§14](#14--nouveautés-v06-issue-3--suite)). La validation
  contact par contact reste disponible en parallèle.
- **Bouton 📍 Carte** : si les GPS n’ont jamais été mémorisés pour la session,
  choisissez une fois le point (pick carte ou create/reuse) pour les enregistrer.
- **SSD / disques EXFAT sous Windows** : le renommage et le TE×10 y sont
  souvent lents ou instables. Copier la nuit sur un volume NTFS (disque local)
  avant de préparer ; voir [§12](#12--questions-fréquentes--dépannage).

---

## 14 · Nouveautés v0.6 (résumé) & suite

Rappel des apports de la **v0.6** (détail dans le flux ci-dessus) :

| Zone | Ce qui change |
|------|----------------|
| Meta / carte | **🗺️ Choisir sur la carte…**, GPS en manifest, libellés humains, **📍 FOCUS** (pin rose), **🔄 Recharger** = tous les sites |
| Validation | **🌊 ChiroSurf nuits** (1 CSV / nuit bio) + validation contact-par-contact inchangée |
| Synthèse | Source `_Vu`, filtre **proba Tadarida ≥** |
| Campagne | **🔧 Vérifier / Réparer** (rapport détaillé, token 401, nettoyage), export **USB** |
| Upload | **Météo non bloquante** (T° Summary auto ; vent/couverture optionnels, complétables sur le portail) |

**Depuis la v0.6** (code local, pas encore de tag de release) :

- **Valider** : tri au clic sur les en-têtes ; filtres taxon observateur et
  **Chiros seulement** (issue #4).
- **Vue session** : bilan `X / Y` ; **Nettoyer** à droite de **Valider** (issue #4.5).
- **ChiroSurf nuits** : ▶ ouvre le CSV brut, 📈 ouvre le `_Vu` (issue #4.8).
- **Activité** : Chiros seulement, taxons observateur, lecture des `_Vu`.
- **Démarrage** : plus de scan auto du dernier dossier ; Préférences →
  « Garder en mémoire le dernier dossier » (issue #5).
- **Upload** : libellés Vent / Couverture nuageuse lisibles.
- **Titley Swift / Ranger** : noms usine `YYYY-MM-DD HH-MM-SS` lus ; TE×10
  sans collision ; Préparer s'arrête si aucun nom n'est lisible (issue #4).
- **Dates** : si le Summary ≠ WAV (carte SD non formatée), avertissement à
  la préparation et avant l'upload ; dates / T° prises sur les fichiers ;
  une participation au mauvais jour n'est pas réutilisée.
- FAQ **EXFAT** (SSD externes sous Windows).

Conception / dev : [`SPEC_v06_parcours.md`](SPEC_v06_parcours.md) · issues
[#3](https://github.com/kevin-guille/ChiroTool/issues/3),
[#4](https://github.com/kevin-guille/ChiroTool/issues/4),
[#5](https://github.com/kevin-guille/ChiroTool/issues/5).

### Suite

- Synthèse `_Vu` « nuit validée statistiquement » (10 % → 75 %), en attente
  du cadrage terrain (issue #3).
- Robustesse / UX du **mode batch**, journal d'upload, export multi-nuits,
  captures tuto (pick carte, ChiroSurf nuits, diagnostic).

---

## 15 · Crédits & licence

**ChiroTool** est un projet **libre et open-source**.

- **Auteur** : GUILLE Kevin — Chargé d'études naturalistes
  [LinkedIn](https://fr.linkedin.com/in/kevin-guille-764b6a150)
- **Avec le soutien de** : [Acer Campestre](https://www.acer-campestre.fr/) —
  bureau d'études en écologie
  ([LinkedIn](https://fr.linkedin.com/company/acer-campestre))
- **Protocole & API** : [Vigie-Chiro / MNHN](https://www.vigienature.fr/fr/chauves-souris)
- **Licence** : MIT (usage et contributions libres)

> 🐙 Code source, bugs et contributions : [github.com/kevin-guille/ChiroTool](https://github.com/kevin-guille/ChiroTool)

---

<div align="center">

*Vous avez des retours, des bugs, des idées ? N'hésitez pas à les remonter.*
*ChiroTool grandit grâce aux utilisateurs de terrain.*

**Bon traitement, et bonnes chauves-souris ! 🦇**

</div>
