# ChiroTool v0.8.5 : activité, lot, sync

Release stable du 2026-10-26.
Les builds 0.8.3 et 0.8.4 ne sont pas publiés.
Cette note reprend leur contenu, et ajoute le seuil de confiance
de l'onglet Activité et le raccourci des nuits déjà analysées
dans l'envoi groupé.
L'exe publié précédent reste la
[v0.8.2](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.2).
Cette release remplace la Latest
[v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1).

`ChiroTool.exe` : 37471903 octets, FileVersion 0.8.5.0, SHA-256
`5653D4FC53D646820AF8B378A2A44BFFAC45C9999B627BA37852068C6E414B4B`.

On remplace l'exe. Dossiers, registre (schéma 3), Suivi, WAV et
participations déjà créées restent.

- Onglet Activité : menu « Confiance min. ». Les lignes sans
  identification humaine passent le seuil de proba Tadarida. Celles
  déjà identifiées (observateur ou validateur) restent. Le menu est
  inutilisé avec « Identifications validées seulement » ou
  « Interprétation _Vu ». Cette relecture ne change pas.
- Envoi groupé : une nuit TERMINE ou FINI sur le portail n'est plus
  listée WAV par WAV, et les fichiers ne sont pas renvoyés. Le tableur
  manquant est téléchargé sans attendre Tadarida. S'il est déjà là,
  la nuit est marquée envoyée. Si l'état ne se lit pas, le listing
  a lieu. Un jeton expiré arrête le lot.
- Un fichier déjà nommé Pass2 n'est plus réécrit Pass1. Le passage
  n'est plus pré-coché à 1. Sans passage choisi, ou repris du Suivi,
  le lot ignore la nuit. Le journal nomme chaque nuit ignorée.
- Un `Data_k` vide n'est plus un envoi réussi. Aucune participation
  n'est créée. Une préparation qui laisse le `Data_k` vide n'est pas
  un succès non plus.
- Une seule instance. La fenêtre de suivi ne bloque plus les autres
  nuits. Les nuits cochées restent prises jusqu'à la fermeture
  de cette fenêtre.
- Métadonnées : heure de début, heure de fin, deux températures,
  vent, couverture. Re-deviner relit le log ou le Summary pour les
  heures et les températures. Le vent saisi reste. Le lot envoie ces
  valeurs sans ouvrir de formulaire. Deux nuits déjà renseignées
  restent distinctes.
- Carte : un carré créé par quelqu'un d'autre apparaît s'il porte une
  de mes participations, ou s'il est déjà mémorisé. Ces points sont
  violets, cliquables dans les 5 km. Les miens restent verts.
- Sync API : le compteur avance sur l'interface, par paquets.
  Fermer la fenêtre arrête la récupération sans écrire le registre.
  Appliquer n'a plus à retélécharger toute la liste.
- Tableur de validation : un enregistrement réécrit un seul fichier
  `participation-<id>-observations_<initiales>.xlsx`. Ouvrir une
  copie déjà suffixée n'en empile plus une autre. Les chaînes
  `_AB_AC` déjà présentes sont retirées à l'enregistrement suivant,
  s'il existe un tableur plus simple. Le téléchargement d'origine
  et une copie à un seul suffixe restent.
- Export vers un autre compte : le manifeste est copié tel quel.
  Si l'identifiant de participation n'est pas éditable avec le compte
  qui envoie, une participation est créée sur ce compte. Un trou de
  réseau ou un jeton expiré laisse l'identifiant en place. Sans
  identifiant dans le manifeste, rien ne change de ce côté.

La pastille verte reste lue sur le dossier de la nuit.
Une nuit que le portail marque déjà terminée n'est pas revérifiée
fichier par fichier.

Pour ce type d'analyse, se reporter à ChiroSurf.
La relecture d'un `_Vu` ne change pas.
