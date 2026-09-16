# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Les versions publiées suivent le SemVer du fichier `version.py` / tags GitHub.

## [Unreleased]

## [0.8.1] - 2026-09-16

`version.py` = `0.8.1`. La pre-release [v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0)
reste l'exe GitHub tant que le tag `v0.8.1` n'est pas créé (après rebuild).
Cumul depuis le 10 septembre : export USB Data_k-only, participation Titley
([#8](https://github.com/kevin-guille/ChiroTool/issues/8)), retours du 16
septembre ([#9](https://github.com/kevin-guille/ChiroTool/issues/9),
[#10](https://github.com/kevin-guille/ChiroTool/issues/10)).

### Ajouté

- **Participation Titley / issue #8** : le wizard envoie le n° de série
  (`detecteur_enregistreur_serie`), le type et le micro à Vigie-Chiro.
  Un `log_*.csv` Titley dans la session préremplit les horaires
  (`Recording start` / `stop`) et les T° de la fenêtre d'enregistrement.
  `Anabat Ranger` est dans la liste des détecteurs. Le micro n'est pas
  inventé depuis le log (parc matériel, ou saisie).

### Corrigé

- **Upload unitaire / wizard vide (issue #9)** : la fenêtre « Nouvelle
  participation » s'affiche tout de suite. Le pré-remplissage (log Titley,
  Summary) tourne ensuite. Un Data_k de plusieurs milliers de WAV sur
  disque externe ne laisse plus une fenêtre noire. S'il y a un log Titley,
  les WAV ne sont plus listés ni avant le wizard (`inspect_summary_vs_wav`
  sauté) ni pour le pré-remplissage.
- **Activité (issue #10)** : les tableurs sont lus une fois et gardés en
  mémoire. Cocher MNHN / chiros / taxons observateur ne relit plus le
  disque. Un `_Vu` à la racine de session ou dans `Data_k/` est pris en
  compte. Cocher MNHN ne fait plus disparaître les autres carrés de la
  liste. Le premier scan ne descend plus dans les milliers de WAV.
- **Suivi d'upload** : fermer la fenêtre pendant l'envoi la met en
  arrière-plan. Recliquer Upload la rouvre. Le bouton Arrière-plan est
  disponible dès le début, pas seulement pendant l'attente Tadarida.
- **Export USB / réintégration** : un scan d'un paquet Data_k-only (ou d'une
  nuit dont les bruts Data/ ont été nettoyés) prenait le dossier `Data_k/`
  pour la session. Les Excel, le Summary et le manifest restaient invisibles,
  les pastilles restaient jaunes, et **Vérifier / Réparer** affichait
  « pas d'ID participation dans le manifest ». Le parent est maintenant la
  session ; l'ID peut aussi être relu depuis
  `participation-<id>-observations.xlsx`.
- **Pastille jaune après nettoyage** : si les bruts sont encore là, le
  contrôle Titley comparait Data_k (déjà purgé) aux WAV 384 kHz et
  reculait TE×10. La pastille restait jaune et **Préparer** ressortait,
  alors que Vérifier / Réparer disait « aucune action ». Le contrôle ne
  s'applique plus une fois `_stats_before_cleanup.json` présent.
- **T° saisies à la main** : si elles diffèrent du Summary / log Titley,
  elles sont conservées à la réouverture du wizard et envoyées (POST, ou
  PATCH si la participation existe déjà). Le cache plat du manifest est
  normalisé avant l'API (batch / reprise).
- **Vérifier / Réparer** : si la participation est déjà analysée, compare
  série / type / micro / horaires / T° au portail. Champs absents (ou T°
  forcées, ou horaires Titley) : PATCH sans relancer Tadarida. Un PATCH
  météo / matériel est **annulé** si le portail n'est pas lisible (Eve
  remplacerait tout le sous-document).

### Tests

- Prefill Titley sans lister Data_k. Découverte `_Vu` en racine et dans
  Data_k. Cache tableurs (pas de relecture si mtime inchangé). `_Vu` MNHN
  vide n'est pas remplacé par l'xlsx. TE×10 Titley inchangé.

## [0.8.0] — 2026-09-06

Issue [#7](https://github.com/kevin-guille/ChiroTool/issues/7) : interprétation
MNHN 10 % / 75 % dans la Synthèse **et** l'onglet Activité (bandes de
confiance Tadarida). Issue [#4](https://github.com/kevin-guille/ChiroTool/issues/4) :
TE×10 Titley, tout le son. Exe reconstruit le 2026-09-08 et le 2026-09-09
(version inchangée). **Publiée** GitHub le 2026-09-09 en pre-release
([v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0),
SHA-256 `225FD7B1D96740724459A76DB46601FDBC26F667F9D988897023AA3E71964ED7`).
Bilan issues : SPEC §0.1 (#4) et §0.2 (#7).

### Ajouté

- **Synthèse, méthode MNHN 10 % / 75 %** (issue
  [#7](https://github.com/kevin-guille/ChiroTool/issues/7)) : case distincte
  dans 📊 Synthèse. Reconstitution depuis le `_Vu` : bandes de **confiance
  Tadarida** (pas le temps). Si une validation concordante atteint la
  bande qui couvre 75 % des contacts de l'espèce, toute l'espèce est
  retenue ; sinon, seulement les bandes 10 % qui contiennent un contact
  écouté. « Identifications validées seulement » reste les lignes
  écoutées. SPEC P8.
- **Activité, méthode MNHN 10 % / 75 %** (issue #7 / P8, rebuild 2026-09-09) :
  même case que la Synthèse (`iter_mnhn_contacts`). Distinct de « Validés
  humains seulement ». Sans `_Vu`, rappel dans la barre de statut.

### Corrigé

- **Activité** : un `_Vu` (nuit 1) ne fait plus disparaître les autres
  nuits du tableur. Le `_Vu` remplace **cette nuit seulement**.
- **Synthèse MNHN** : cases ignorées tant que le tableur n'est pas
  chargé ; colonne **75 %** dans le tableau ; export CSV avec
  `Atteint_75` / `F75` / pool / proba illisibles ; libellé de source
  nuit par nuit en cumul ; avertissement si la source n'est pas un
  `_Vu` ChiroSurf. Un `_Vu` illisible ou sans colonnes Vigie-Chiro
  affiche le nom du fichier et replie sur le tableur.
- **Upload code 409** : un WAV déjà enregistré n'est plus un échec. Il est
  sauté et Tadarida peut partir. Cas typique : l'envoi a créé les fiches,
  puis s'est interrompu (réseau ou saturation) avant l'analyse.
- **Vérifier / Réparer** : si le portail n'arrive pas à lister les fichiers,
  sonde les noms Data_k. Tous déjà enregistrés (code 409) : propose de
  lancer Tadarida au lieu d'un re-upload bloqué. Si l'analyse sort 0 contact,
  le son n'est probablement pas sur le serveur (nouvelle participation).
- **Afficher le bureau (Win+D)** : les fenêtres de progression / wizards
  réapparaissent en recliquant ChiroTool (plus besoin de tuer le process).
  Sous Windows, elles ont aussi une icône dans la barre des tâches.
- **TE×10 Titley / Wildlife (issue #4, rebuild 2026-09-09)** : le moteur
  Rust n'incrémentait pas l'heure des tranches de 5 s en fin de nom.
  Un WAV de 12 à 15 s ne gardait que les 5 premières secondes. Un Data_k
  tronqué n'est plus marqué « TE×10 fait » (upload grisé).

### Tests

- Bandes / F75 (graphe 102 / 71 / 78), bande F75 sautée, correction
  Eptser → MyoGT, fixture Benjamin Nuit_1 (`Pippip` 184, `Pipkuh` 73).
- `_Vu` nuit 1 + xlsx nuit 2 : les deux nuits restent dans Activité.
- Upload 409 = déjà enregistré ; repair sonde titres ; restauration
  des fenêtres après Afficher le bureau.
- Activité MNHN : totaux graphe = Synthèse (71 / 102). TE×10 Titley :
  3 dest distincts, Data_k tronqué refusé.

### Documentation

- Pre-release GitHub [v0.8.0](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.0)
  (2026-09-09). Notes 0.7.1 / 0.7.2 : plus courantes. Liens de
  téléchargement vers le tag (GitHub Latest reste 0.7.2 tant que 0.8.0
  est pre-release).

## [0.7.2] — 2026-09-01

Correctifs terrain après 0.7.0 / pre-release 0.7.1
([#7](https://github.com/kevin-guille/ChiroTool/issues/7)).

### Corrigé

- **Vue session** : barre d'actions sur **une ligne**, glissement horizontal
  si le panneau est trop étroit (plus rien de coupé après 📍 Carte). Dans
  **ChiroSurf nuits**, les boutons ▶ / 📈 / Synthèse passent sous le libellé,
  alignés à gauche.
- **Synthèse / nuit biologique (D12)** : une pose qui passe **minuit**
  (soir + matin) est **une** nuit. Plus de sélecteur « Nuit 1 / Nuit 2 »
  fantôme (l'ancien fallback date calendaire sans heure scindait à minuit).
  Les vraies participations multi-nuits (2 soirs) restent scindées à midi.

### Tests

- Pose 21 h → 6 h = 1 slice ; suffixe / espace dans le nom ; Titley overnight ;
  ligne sans horodatage n'invente pas une Nuit 2.

### Documentation

- SPEC D12 (règle de nuit, anti-patterns) ; tutoriel §8/§9/FAQ ; README ;
  landing ; note [`docs/RELEASE_v0.7.2.md`](docs/RELEASE_v0.7.2.md).

## [0.7.1] — 2026-08-31

Issue [#7](https://github.com/kevin-guille/ChiroTool/issues/7)
(Benjamin — liaison ChiroSurf).

### Corrigé

- **▶ ChiroSurf** (fenêtre nuits) : le CSV est copié à côté des WAV
  (`Data_k/` sinon `Data/`) avant lancement. ChiroSurf 4.x glob
  `*.{wav,mp3}` dans le dossier du tableur ; un CSV isolé dans
  `chirosurf/` faisait planter le script de démarrage (Tcl
  *no files matched glob pattern*). S'il n'y a aucun WAV, l'ouverture
  est refusée avec un message clair (nuit déjà nettoyée).
- **`_Vu` hors ChiroTool** : reconnaissance de `Nuit1_`, `Nuit_1_` et
  `Nuit_1-` ; un `_Vu` collé dans `chirosurf/` ou écrit par ChiroSurf
  dans `Data_k/` (à côté du CSV ouvert) est listé, rapatrié vers
  `chirosurf/`, et lu par Synthèse / Activité.

### Tests

- Naming Benjamin (`Nuit_1-observations_Vu.csv`) + préfixe avant
  `participation`.
- Staging CSV → `Data_k/` ; refus sans WAV ; harvest `_Vu`.

### Documentation

- Tutoriel §8 B + FAQ issue #7 ; landing / README / SPEC / CONTRIBUTING.
- Note de pre-release [`docs/RELEASE_v0.7.1.md`](docs/RELEASE_v0.7.1.md)
  (SHA-256 de l'exe).

## [0.7.0] — 2026-08-30

Retours issues [#4](https://github.com/kevin-guille/ChiroTool/issues/4),
[#5](https://github.com/kevin-guille/ChiroTool/issues/5),
[#6](https://github.com/kevin-guille/ChiroTool/issues/6).

### Ajouté

- **Valider** : tri au clic sur les en-têtes (asc / desc / ordre d'origine) ;
  filtre « Taxon observateur renseigné uniquement » ; filtre **Chiros
  seulement** (issue #4).
- **Vue session** : bilan `X / Y` contacts avec taxon observateur (xlsx en
  arrière-plan, cache) et nombre d'identifications déjà envoyées si sidecar.
- **Synthèse** : sélecteur de **nuit biologique** (indépendant de ChiroSurf) ;
  `_Vu` lu s'il existe ; cumul multi-nuits sans classes d'activité
  (contacts/nuit).
- **ChiroSurf nuits** : ouverture du CSV brut (▶ ChiroSurf) et du `_Vu`
  (📈 graphes) depuis la liste des nuits et depuis Valider (issue #4.8) —
  **optionnel**, distinct de la Synthèse.
- **Activité** : filtres **Chiros seulement** et **Taxons observateur** ;
  lecture des CSV `_Vu` (issue #4.9–10).
- **Titley Swift / Ranger** (issue #4) : noms usine `YYYY-MM-DD HH-MM-SS`
  (espace ou underscore, ± n° d'enregistreur) lus au renommage ; TE×10
  incrémente l'heure des tranches ; **Préparer s'arrête** si aucun nom
  n'est lisible.

### Corrigé

- **Valider** : le 2e clic sur un en-tête conserve le tri (callback heading
  reposé après mise à jour du libellé ▲ / ▼).
- **Vue session** : bouton **Nettoyer** à droite de **Valider** (issue #4.5) ;
  **📊 Synthèse** avant **🌊 ChiroSurf nuits** (complémentaires, pas un
  remplacement).
- **Upload / participation** : libellés Vent et Couverture nuageuse lisibles
  (titre + aide empilés, plus superposés).
- **Démarrage** (issue #5) : plus de scan auto du dernier dossier (EXFAT /
  SSD endormi figeait l'UI et grisait Parcourir). Préférences → Général :
  « Garder en mémoire le dernier dossier » (coché par défaut) ; décoché,
  le chemin n'est plus restauré. Parcourir reste cliquable pendant un scan.
- **Dates Summary vs une nuit** (Jeanne) : si le Summary ne correspond pas
  aux WAV (carte SD non formatée, pose cumulée), **avertissement** à la
  préparation et avant l'upload ; dates (et T° si recoupement) prises sur
  les fichiers ; une participation déjà créée au mauvais jour n'est plus
  réutilisée.

### Documentation

- Tutoriel + PDF : distinction Synthèse / ChiroSurf ; coupure **midi** (nuit
  biologique) ; Titley ; dates Summary ≠ WAV ; démarrage sans scan auto ;
  SM2 / `.wac` / `.w4v` (issue [#6](https://github.com/kevin-guille/ChiroTool/issues/6)).
- README + landing GitHub Pages : v0.7.

### Tests

- TE×10 : un WAV de 15 s raw produit **3** segments (pas de troncature).
- Cohérence synthèse / compteur observateur sur le `_Vu` Nuit_1 issue #3.
- Titley : parse noms, rename, TE×10 15 s sans collision, stop si illisible.
- Dates Jeanne : Summary multi-jours → WAV ; participation périmée non réutilisée.
- Nuit biologique : coupure midi ; sélecteur Synthèse (Nuit 1 / toutes).

## [0.6.0] — 2026-08-07

Issue [#3](https://github.com/kevin-guille/ChiroTool/issues/3) (retours terrain)
+ SPEC [`docs/SPEC_v06_parcours.md`](docs/SPEC_v06_parcours.md).

### Ajouté

- **Vérifier / Réparer** (une nuit) : diagnostic local ↔ serveur, alignement
  flags, fetch xlsx / relance Tadarida **avec confirmations**.
- **Export portable de sessions** (Registre → Sessions USB) : Data_k ± Data +
  métadonnées, estimation de volume, paquet horodaté.
- **PointSelection** + GPS dans le **manifest** (lat/lon, site_id, commune).
- **Mode pick carte** depuis l’assistant métadonnées (« 🗺️ Choisir sur la carte… ») :
  commune, points dans **5 km**, create/reuse → champs remplis.
- **FOCUS 📍 Carte** : recentrage sans full-API (manifest → active_point → cache),
  marqueurs du projet/dossier + highlight de la nuit.
- **ChiroSurf multi-nuits** (lazy) : bouton **🌊 ChiroSurf nuits** → dossier
  `chirosurf/Nuit{n}_…-observations.csv` (nuit biologique, coupure midi) ;
  ouverture dossier ; synthèse par nuit / `_Vu`.
- **Synthèse** : filtre **proba Tadarida minimale** ; source xlsx ou `_Vu`.
- Modules `point_selection.py`, `chirosurf_nights.py` (tests unitaires).

### Corrigé

- **Point actif** create **et** reuse (y compris autre observateur) mémorisé
  pour le wizard meta (parcours carte → préparer).
- Upload « tous WAV déjà sur serveur » : plus de flag `uploaded` silencieux ;
  journalisation `trigger_compute`.
- **📍 FOCUS carte** : ne plus être écrasé par le chargement API (vue France) ;
  pin rose unique `★ Zx` / `★ Zx · N nuits` ; **🔄 Recharger sites** sort du
  FOCUS et montre tous les sites ; fiche point avec bouton bas toujours visible.
- **Vérifier / Réparer** (retours beta) :
  - pagination `/fichiers` + **`max_results=99`** (plafond Eve) ;
  - fallback titres via `/participations/<id>/donnees` ;
  - token **401** : message clair, pas de re-upload massif fantôme ;
  - couverture = WAV **encore dans Data_k** ; purges nettoyage = info
    « sur serveur seul » (ex. 185 fichiers).
- **Météo participation non bloquante** (retours terrain) : vent / couverture
  et T° vides n'empêchent plus l'upload ; Summary continue de préremplir les
  T° ; pas de valeur inventée ; complétion possible plus tard sur le portail.

### Documentation

- Tutoriel v0.6 (meta/carte FOCUS, ChiroSurf nuits, repair/token, météo
  optionnelle, FAQ) + PDF régénéré.
- SPEC, samples issue #3, CONTRIBUTING, README, landing GitHub Pages.

### Suite possible (post-0.8)

Ne pas relire le 1er message des issues
[#4](https://github.com/kevin-guille/ChiroTool/issues/4) (SPEC §0.1) et
[#7](https://github.com/kevin-guille/ChiroTool/issues/7) (SPEC §0.2) comme
backlog. **Pas plusieurs exe** (D14) : le mode Batch enchaîne les nuits
dans une instance.

- Robustesse / UX **mode batch** (données complémentaires participation,
  template avant lot, journal d'upload).
- Export multi-nuits compilé (espèces × nuits).
- Fusion `_Vu` → xlsx (choix produit : la méthode 10 % / 75 % n'alimente pas
  l'envoi Vigie-Chiro aujourd'hui).
- Modes export formalisés Léger / Travail / Complet.

## [0.5.0] — 2026-07-19

Voir la [release GitHub](https://github.com/kevin-guille/ChiroTool/releases) et
le message de tag `v0.5.0` (token sécurisé, nettoyage renforcé, envoi des
identifications, synthèse / activité, etc.).
