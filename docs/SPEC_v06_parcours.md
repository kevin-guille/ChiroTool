# Spécification parcours — PointSelection, carte, ChiroSurf (post-0.5)

| | |
|--|--|
| **Statut** | **Implémenté en v0.6.0** (conception validée + code livré) |
| **Date** | 2026-08-04 |
| **Contexte** | Issue [#3](https://github.com/kevin-guille/ChiroTool/issues/3) (Benjamin Drillat) + retours carte / meta |
| **Principe** | Pragmatisme — une vérité disque, peu de fichiers, parcours unifiés, libellés humains d’abord |

Ce document **prime** sur l’improvisation au codage. En cas de doute : revenir ici, ou amender le §8 avant de coder autre chose.

**Public** : développeurs / mainteneur. Le tutoriel utilisateur (`TUTORIEL.md`) ne reprend les parcours qu’**après** livraison de chaque vague.

---

## 0. Décisions actées

| # | Décision |
|---|----------|
| D1 | **PointSelection** = contrat unique (récents / pick carte / saisie manuelle → meta). |
| D2 | **Pas de double carte** : le module carte existant a deux *intentions* (browse vs pick), un seul code. |
| D3 | **Fichiers ChiroSurf lazy** : dossier `chirosurf/` créé à la demande, 1 CSV / nuit biologique. |
| D4 | **1 dossier session = 1 participation** (souvent multi-nuits). On ne scinde pas le FS en N sessions-nuits. |
| D5 | **Export en 3 modes** : Léger / Travail / Complet (pas une usine à cases). |
| D6 | **Libellés humains d’abord** ; n° de carré / Zx en secondaire (toujours visibles). |
| D7 | **« 📍 Carte » (vue session)** : **on garde le bouton**, on le **répare** — pas de France vide. Voir §2. |
| D8 | Coordonnées GPS **persistées** dans le manifest de session dès qu’un point est choisi/créé/réutilisé (sinon « Voir sur la carte » reste fragile). |
| D9 | Validation contact-par-contact **conservée** ; méthode ChiroSurf 10 %→75 % en **complément**. |
| D10 | Rayon de chargement mode **PICK** = **5 km** (constante unique, ajustable plus tard si retour terrain). |
| D11 | Naming CSV nuit : **préfixe** `Nuit{n}_` + stem d’origine (voir §1.2.1) — aligné usage Benjamin + contrainte ChiroSurf `_Vu`. |

---

## 1. Contrats de données (cibles)

### 1.1 PointSelection (mémoire de travail + dernier choix)

```
PointSelection {
  label_humain   # "Vif · Z1 · carré 381009" (+ "autre obs." si besoin)
  site_numero    # 6 chiffres Tadarida / STOC
  point_code     # Z1, A2…
  lat, lon       # obligatoires dès qu’on sort du pick/create/reuse
  site_id        # id API Vigie-Chiro (si connu)
  provenance     # mine | other | created
  commune        # optionnel, reverse geocode ou Nominatim
}
```

- **Retour de valeur** vers le wizard meta (contrat principal).
- **active_point.json** = cache du dernier PointSelection (reprise, badge ★) — **bonus**, pas pilier.
- À la validation meta / prepare : **écrire lat/lon (+ site_id, point, numero)** dans le **manifest session**.

### 1.2 Fichiers session (vérité + dérivés)

```
<session>/
  _session_manifest.json          # vérité méta (+ lat/lon point une fois connus)
  participation-…-observations.xlsx
  Data_k/   Data/                 # audio
  chirosurf/                      # ABSENT par défaut ; créé au 1er besoin ChiroSurf
    Nuit1_<stem>-observations.csv
    Nuit1_<stem>-observations_Vu.csv   # produit par ChiroSurf (même dossier)
    Nuit2_<stem>-observations.csv
    …
```

- Nuit = **nuit biologique** (coupure à midi) — validé sur les CSV Benjamin (8000 + 7839 = multi).
- Ordre `Nuit1`, `Nuit2`… = ordre chronologique des nuits bio dans la participation.
- UI : toujours afficher aussi la **date** (`28/07 · Nuit 1 · ~8000 contacts`).
- Régénérer les CSV **bruts** = OK (écraser). **Ne jamais écraser un `_Vu`** sans confirmation.
- Workflow ChiroSurf (forum Yann T.) : on ouvre le CSV **sans** `_Vu` ; le `_Vu` est mis à jour dans le **même dossier** ; pour reprendre, rouvrir le brut.

#### 1.2.1 Naming CSV — décision (D11) + sources

**Contrainte ChiroSurf** (forum, fil téléchargement ChiroSurf) : le fichier validé est le même stem avec suffixe **`_Vu` juste avant `.csv`**. Tant que le `_Vu` reste à côté du brut, on peut poursuivre en rouvrant le CSV *sans* `_Vu`.

**Demande Benjamin (issue #3)** : scinder « en gardant son **nom d’origine à la fin** » pour que ChiroSurf le lise encore.

**Fichiers qu’il a fournis** (usage réel + round-trip `_Vu` prouvé) :

```
Nuit_1_<id>-participation-<id>-observations.csv
Nuit_1_<id>-participation-<id>-observations_Vu.csv
Nuit_2_…  (idem)
```

→ marqueur de nuit en **préfixe**, stem portail **à la fin**, `_Vu` inséré avant `.csv`.

**Forum [t483 — plusieurs nuits consécutives](https://vigie-chiro.forumactif.com/t483-chiro-surf-analyser-plusieurs-nuits-consecutives)** (Yann T. / Yves Bas / LouSauvajon) :

| Point | Implication pour nous |
|-------|------------------------|
| Unité référentiels = **nuit unique complète** | Split par nuit bio = bon chemin (pas un caprice) |
| ChiroSurf « oblige pour l’instant à scinder **avant** » pour une validation optimisée propre | Notre split lazy est aligné Team Chiro / usage terrain |
| Alternative v4.1+ : valider un multi-nuits d’un coup avec **biais** (moyenne, favorise « modéré », ≤ ~5 nuits) | On ne s’y appuie pas comme défaut ; on reste sur 1 CSV / nuit |
| Idéal protocolaire (Yann) : 1 nuit → 1 participation → 1 CSV → 1 `_Vu` | ChiroTool ne force pas à re-découper les participations VC ; on scinde **en local** pour ChiroSurf |
| Pas de **convention de nom officielle** pour les scissions | On s’aligne sur l’exemple Benjamin (seul round-trip `_Vu` multi-nuits en notre possession) |

**Variante « `_Nuit1` en fin de nom »** (`…-observations_Nuit1.csv`) : probablement OK pour ChiroSurf (`…_Nuit1_Vu.csv`), mais :

- contredit la formulation issue #3 (« nom d’origine **à la fin** ») ;
- s’éloigne des fichiers que Benjamin a déjà produits et validés ;
- un peu plus pénible à reconnaître dans l’explorateur (tout se ressemble jusqu’au bout).

**Convention retenue (D11)** :

```
Nuit{n}_{stem_origine}.csv
Nuit{n}_{stem_origine}_Vu.csv     # écrit par ChiroSurf
```

Ex. :

```
chirosurf/Nuit1_444976…-participation-…-observations.csv
chirosurf/Nuit1_444976…-participation-…-observations_Vu.csv
```

- `{n}` = 1, 2, 3… (chrono).
- Date de nuit = **métadonnée UI** (+ éventuellement fichier index JSON interne si besoin) ; pas obligatoire dans le nom si le stem d’origine + NuitN suffisent. Si un jour on veut le tri purement alphabétique par date : `Nuit{n}_{YYYYMMDD}_{stem}` — **non requis en v1**.
- Constante rayon pick : **`PICK_RADIUS_KM = 5`**.

### 1.3 Export (3 modes)

| Mode | Contenu | Usage |
|------|---------|--------|
| **Léger** | manifest + xlsx + `chirosurf/` + sidecars / stats | synthèse, relecture, collègue |
| **Travail** | Léger + **Data_k** | validation acoustique hors poste |
| **Complet** | Travail + **Data** | archive / reprocess |

Les CSV ChiroSurf sont cheap (≈ 0,5–2 Mo/nuit) : toujours emportés s’ils existent dans le mode Léger+.

---

## 2. « 📍 Carte » depuis la vue session (aparté intégré)

### 2.1 Constat (bug actuel)

- Bouton **📍 Carte** → onglet Carte + `load_sites_async()` + `focus_on_session` après **300 ms**.
- `focus_on_session` ne regarde que `_sites_cache` (points **API user** déjà chargés).
- Si le cache n’est pas prêt, ou point d’un **autre obs.**, ou pas de match site/point → message « non géolocalisé » et **vue France** : inutilisable.
- Charger **toute** l’API user **uniquement** pour recentrer un point est disproportionné (Benjamin : beaucoup de points).

### 2.2 Décision : garder le bouton, changer la stratégie

**Ne pas retirer** le bouton : le besoin (« où est cette nuit ? ») est légitime.  
**Ne pas** dépendre d’un full-fetch API pour ce geste.

#### Comportement cible — mode **FOCUS session** (browse, pas pick)

1. Bascule onglet **Carte**.
2. Résout les coordonnées du point de la nuit, **dans cet ordre** :
   1. `lat`/`lon` dans le **manifest** de la session (D8) ;
   2. sinon PointSelection / active_point frais **même site+point** ;
   3. sinon entrée déjà en cache carte (sites chargés) ;
   4. sinon : message clair *« Coordonnées inconnues — utilisez une fois “Choisir sur la carte” ou le pick pour les mémoriser »* + **pas** de zoom France trompeur (rester vue courante ou France seulement si 1ʳᵉ ouverture carte sans focus).
3. **Centre + zoom** (~15) sur ce point.
4. Marqueurs affichés pour ce focus (sans attendre le bulk API) :
   - **Tous les points du même projet/dossier (campagne)** pour lesquels on a déjà des coords (manifests des sessions du contrat / parent) — marqueurs discrets ;
   - **Point de la nuit cliquée** mis en avant (couleur / taille / popup auto ou status « 📍 Vif · Z1 · cette nuit »).
5. Chargement API user **non bloquant** et **non requis** pour ce focus. S’il arrive plus tard et enrichit le cache, tant mieux ; il ne doit pas retarder ni casser le recentrage.

#### Ce qu’on refuse ici

- Timeout magique 300 ms + espoir.
- Full download de tous les sites VC pour un seul focus.
- Bouton zombie qui ouvre la France.

#### Lien avec le mode pick

| Intention | Entrée | Charge | But |
|-----------|--------|--------|-----|
| **FOCUS** | 📍 Carte (vue session) | Local (manifests campagne) + highlight | « Où est *cette* nuit ? » |
| **PICK** | Wizard meta → « Choisir sur la carte… » | Commune + mes points ~5–10 km ; au create : points du **carré** (moi + autres) | Choisir / créer / réutiliser un point → retour PointSelection |
| **BROWSE** | Onglet Carte libre | Cache sites user (existant) | Exploration / historique saison |

---

## 3. Parcours utilisateurs figés

Légende fichiers : `+` créé · `~` modifié · `=` inchangé · `→` lecture seule.

---

### P1 — Préparer une nuit, point déjà connu (happy path rapide)

**Acteur** : observateur qui refait un point habituel.

1. Sélectionne la nuit dans la liste → vue session.
2. **▶ Préparer** → meta devinée OK **ou** wizard avec **⭐ Récents** (libellé humain).
3. Choisit le récent → champs site/point (et lat/lon si connus) remplis.
4. Complète date / passage / enregistreur si besoin → **Valider**.
5. Rename + TE10 comme aujourd’hui.

**Fichiers** : `~` manifest (meta + lat/lon si absents) · `+`/`~` Data_k.

**Hors scope P1** : pas de `chirosurf/`.

---

### P2 — Préparer : choisir / créer le point sur la carte (pick)

**Acteur** : nouveau lieu, ou point d’un collègue, ou refus des numéros de carré en premier.

1. **▶ Préparer** (ou **✎ Métadonnées**) → wizard.
2. Clic **🗺️ Choisir sur la carte…** → carte en **mode PICK** (focus UI, pas un clone de module).
3. Recherche **commune / lieu** (Nominatim existant) → zoom.
4. Charge **mes points dans 5 km** (`PICK_RADIUS_KM = 5`, D10).
5a. **Clic marqueur existant (mien)** → confirmer → **PointSelection** → retour wizard, champs remplis.  
5b. **Clic vide / Créer ici** → résolution carré STOC (API) →
    - aperçu **tous les points du carré** (vert = moi, orange = autres) ;
    - si proche d’un existant → proposer **réutiliser Zx** (distance, logique actuelle) ;
    - sinon → **créer** mon point ;
    - confirm API → PointSelection → retour wizard.
6. Valide meta → prepare.

**Fichiers** : `~` active_point (cache) · `~` sites externes si other · `~` manifest session (lat/lon + ids).

**Échecs acceptables** : pas de token → message + lien préférences ; hors grille STOC → stop avec explication (déjà en place).

---

### P3 — « 📍 Carte » depuis une nuit déjà préparée (focus)

**Acteur** : « Je veux voir où est cette session dans mon dossier. »

1. Vue session → **📍 Carte**.
2. Comportement §2.2 (coords manifest prioritaires, marqueurs **campagne**, highlight nuit).
3. Optionnel : depuis le popup du point, **Utiliser pour la prochaine préparation** (déjà là) → alimente active_point / récents.

**Fichiers** : `=` aucun écrit obligatoire.

**Si coords inconnues** : pas de mensonge France ; message d’action (refaire un pick une fois).

---

### P4 — Participation multi-nuits → validation ChiroSurf (méthode MNHN)

**Acteur** : Benjamin / LPO — 10 %→75 % nuit par nuit.

1. Session avec xlsx observations (1 participation, N nuits bio).
2. Zone **Validation** : conserver **Valider** (contact-par-contact) **et** entrée **ChiroSurf (nuits)**.
3. Premier usage → crée `chirosurf/` + 1 CSV brut / nuit bio (lazy, depuis xlsx), naming **D11** (`Nuit{n}_{stem}.csv`).
4. UI liste : `28/07 · Nuit 1 · ~8000 contacts · [Ouvrir dossier] [Importer _Vu]` (etc.).
5. Utilisateur ouvre le CSV **sans** `_Vu` dans ChiroSurf (même dossier que les WAV / Data_k selon config CS) → produit `Nuit{n}_{stem}_Vu.csv`.
6. **Importer _Vu** → synthèse (et éventuellement fusion vers copie de travail locale ; pas d’upload forcé).
7. Validation contact-par-contact reste disponible sur l’xlsx (D9).

**Fichiers** :
- `+` `chirosurf/Nuit{n}_{stem}-observations.csv` (N nuits)
- `+` `chirosurf/Nuit{n}_{stem}-observations_Vu.csv` (par ChiroSurf)
- `=` pas de multi-CSV permanent en plus du split

**Non-objectifs** : piloter l’UI interne de ChiroSurf ; auto-split à chaque fetch ; valider multi-nuits d’un bloc avec biais (piste ChiroSurf 4.1, pas notre défaut).

---

### P5 — Synthèse avec _Vu + filtre proba

1. Ouvre **📊 Synthèse**.
2. Source : xlsx **ou** `_Vu` de la nuit choisie si multi et importé.
3. Option **identifications validées seulement** (existant).
4. **Nouveau** : seuil **proba Tadarida minimale** (synthèse non validée).
5. Référentiels d’activité : national / région (déjà via n° site) / milieu (existant) — **exposer**, ne pas réécrire.
6. Plus tard : export compilé multi-nuits (espèces × nuits) en action explicite.

---

### P6 — Export USB / partage

1. Registre → Exporter → Sessions.
2. Choisit sessions + **mode** Léger / Travail / Complet.
3. Estimation taille → copie paquet horodaté.

**Fichiers produit** : arbre relatif rejouable (déjà `export_sessions.py`) ; inclure `chirosurf/` s’il existe.

---

### P7 — Repair (déjà codé, à shipper)

1. Pastille ⏳ ou **🔧 Vérifier / Réparer**.
2. Diagnostic local ↔ serveur → actions confirmées (download xlsx, flags, relance Tadarida…).

Indépendant de P2–P5 ; livrable Vague A.

---

## 4. Attentes vs faisabilité

| Attente | Faisable ? | Commentaire |
|---------|------------|-------------|
| PointSelection + retour wizard | **Oui** | Refacto flux meta ; s’appuie sur active_point / AddPointWizard |
| Pick : commune + rayon **5 km** (D10) | **Oui** | Nominatim + filtre distance sur cache ; API ciblée si besoin |
| Naming `Nuit{n}_` + stem (D11) | **Oui** | Prouvé par fichiers Benjamin + règle `_Vu` forum |
| Create/reuse carré + distance | **Oui** | Déjà en place (`resolve_carre`, wizard site) |
| Persister lat/lon manifest | **Oui** | Extension meta ; rétrocompat lecture |
| FOCUS sans full API | **Oui** | Priorité coords locales ; marqueurs campagne via manifests |
| Marqueurs « tout le projet/dossier » | **Oui** | Sessions du même parent/contrat + meta GPS ; pas besoin VC |
| Highlight nuit courante | **Oui** | Style marker + status/popup |
| Split lazy nuit bio | **Oui** | Logique pure (même coupure midi que `activity_graph`) ; fixtures Benjamin |
| Import `_Vu` → synthèse | **Oui** | Même 11 colonnes ; proba obs SUR/PROBABLE |
| Ouvrir ChiroSurf « magiquement » sur le bon CSV | **Partiel** | Générer fichier + ouvrir dossier (fiable). Lancement exe + args dépend de ChiroSurf — ne pas promettre plus |
| Filtre proba min synthèse | **Oui** | Petit delta `synthesis` + GUI |
| Référentiels régionaux | **Déjà** | Brancher l’UI si pas assez visible |
| Export 3 modes | **Quasi** | Wizard export existe ; formaliser libellés modes |
| Ne plus jamais charger l’API carte | **Non** | Browse / pick create ont encore besoin de l’API ; FOCUS non |
| Carte 100 % offline pour create point | **Non** | `resolve_carre` + create site = API |
| Auto-organisation multi-contrats / sites d’étude dans un contrat | **Plus tard** | Demandé par Benjamin en exploration — hors v0.6 cœur |

---

## 5. Ce qu’on ne fait pas (anti-scope)

- Auto-génération CSV ChiroSurf à chaque fetch.
- N dossiers session = N nuits biologiques.
- Deux widgets carte (wizard embarqué + onglet).
- 15 options d’export.
- Rayon 5 km qui **cache** les points des autres **dans le carré** en création (doublons).
- Remplacer la validation contact-par-contact.
- Promettre un pilotage complet de ChiroSurf.

---

## 6. Ordre de livraison proposé

| Vague | Contenu | Dépendances |
|-------|---------|-------------|
| **A — Ship** | Repair + export USB + fix reuse/create → active_point (commits locaux) | Push / release notes / réponse issue #3 |
| **B — Point** | D8 lat/lon manifest · PointSelection · wizard 3 entrées · **FOCUS carte (§2)** · mode PICK branché | A optionnel mais souhaitable |
| **C — ChiroSurf** | Split lazy · UI nuits · import `_Vu` · synthèse proba min | Fixtures `samples/issue3_benjamin/` |
| **D — Polish** | Export multi-nuits compilé · libellés région · tutoriel captures | B+C |

Le codage ne démarre qu’après **validation explicite** de ce document (éventuels amendements notés ci-dessous).

---

## 7. Impacts doc produit (quand on code)

| Doc | Quand | Quoi |
|-----|-------|------|
| `CHANGELOG.md` | Chaque vague | Entrées user-facing |
| `docs/TUTORIEL.md` | Ship B/C | Parcours pick, focus carte, ChiroSurf nuits |
| `README.md` | Ship | 1–2 lignes features |
| Issue #3 | A + C | Réponse + capture d’écran si possible |
| **Ce fichier** | Amendements conception | Historique en §8 |

Le tutoriel **ne décrit pas** les features non livrées comme déjà disponibles.

---

## 8. Amendements

| Date | Auteur | Change |
|------|--------|--------|
| 2026-08-04 | conception | Version initiale figée (parcours + FOCUS carte + ChiroSurf lazy) |
| 2026-08-04 | conception | D10 rayon pick **5 km** ; D11 naming `Nuit{n}_`+stem (forum t483 + pièces Benjamin) ; rejet suffixe `_Nuit1` comme défaut |
| 2026-08-04 | doc | Statut **Validé** ; relais README / CHANGELOG / TUTORIEL §14 / samples README / CONTRIBUTING |
| 2026-08-04 | doc | Tutoriel : pick intégré §6, ChiroSurf nuits §8 B, synthèse proba, FAQ ; README features |
| 2026-08-04 | beta | FOCUS carte survit au load sites ; Recharger = tous sites ; repair token 401 + max_results 99 ; popup bouton bas ; pin unique multi-nuits |

---

## 9. Références

- Issue #3 — méthode validation MNHN, multi-nuits, pièces CSV Benjamin.
- Échantillons : `samples/issue3_benjamin/` (multi + Nuit_1/2 + `_Vu`).
- Forum Vigie-Chiro :
  - [t483 — analyser plusieurs nuits consécutives](https://vigie-chiro.forumactif.com/t483-chiro-surf-analyser-plusieurs-nuits-consecutives) (Yann T., Yves Bas, LouSauvajon)
  - [t108 — ChiroSurf téléchargement / `_Vu` même dossier](https://vigie-chiro.forumactif.com/t108-chirosurf-4-5-telechargement-audible-ultrasons-basses-frequences-09-07-26)
  - [t407 — webinaire validation ChiroSurf](https://vigie-chiro.forumactif.com/t407-webinaire-comment-valider-ses-donnees-avec-chirosurf)
- Code actuel utile : `gui_map.py` (focus_on_session, add point, active_point), `gui_wizard.py`, `gui_app._view_on_map`, `export_sessions.py`, `activity_graph._night_date_iso`, `synthesis.py`, `activity_reference.py`.
