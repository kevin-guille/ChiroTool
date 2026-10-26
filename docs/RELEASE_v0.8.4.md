# ChiroTool v0.8.4 : lot, sync, tableur

**Non publiée.** Le contenu est repris par la release stable 0.8.5.
Les deux limites en fin de note (listing du lot, seuil Activité)
sont levées dans cette 0.8.5.

Pré-release locale du 2026-10-22. La 0.8.3 n'est pas publiée.
Cette note reprend son contenu, et ajoute la sync, le tableur
de validation et l'export vers un autre compte.
À la date de ce build, la Latest était la
[v0.8.1](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.1).
La Latest est maintenant la
[v0.8.5](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.5).
L'exe publié précédent reste la
[v0.8.2](https://github.com/kevin-guille/ChiroTool/releases/tag/v0.8.2).

`ChiroTool.exe`, 37469168 octets, SHA-256
`EA70113C659FE8A5A8955BB278FFF59F3F71D18D09BC76C416F6FC010FF96A15`.

On remplace l'exe. Dossiers, registre (schéma 3), Suivi, WAV et
participations déjà créées restent. L'exe 0.8.2 n'a pas ces gardes.

- Un fichier déjà nommé Pass2 n'est plus réécrit Pass1. Le passage
  n'est plus pré-coché à 1. Sans passage choisi, ou repris du Suivi,
  le lot ignore la nuit. Le journal nomme chaque nuit ignorée.
- Un `Data_k` vide n'est plus un envoi réussi. Aucune participation
  n'est créée. Une préparation qui laisse le `Data_k` vide n'est pas
  un succès non plus.
- Un jeton expiré arrête le lot. Les fichiers pas encore partis ne
  partent pas. Les nuits suivantes ne démarrent pas.
- La fenêtre de suivi ne bloque plus les autres nuits. Une seule
  instance. Les nuits cochées restent prises jusqu'à la fermeture
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

Le saut de comparaison des WAV, quand le portail dit la nuit déjà
analysée, reste dans Vérifier / Réparer. Il n'est pas dans l'envoi
groupé. Pas de seuil de confiance sur l'onglet Activité.

Pour ce type d'analyse, se reporter à ChiroSurf.
La relecture d'un `_Vu` ne change pas.
