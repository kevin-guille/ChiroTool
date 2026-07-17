# Politique de sécurité

## Token Vigie-Chiro — ne jamais le partager

ChiroTool utilise un **token d'API Vigie-Chiro** (équivalent d'un mot de passe
de votre compte). Il est stocké **chiffré** via le gestionnaire d'identifiants
de Windows (Credential Manager / DPAPI) et **n'apparaît jamais en clair** dans
les fichiers du projet ni dans les logs.

**Ne collez jamais votre token** dans une issue, une pull request, une capture
d'écran ou un fichier de log partagé. Si vous pensez l'avoir exposé,
**régénérez-le** depuis le portail Vigie-Chiro.

### Saisir le token en ligne de commande

Si vous utilisez la CLI, **évitez de mettre le token directement dans la
commande** : il resterait visible dans l'historique du shell et la liste des
processus. Préférez, dans cet ordre :

- la **saisie interactive masquée** : `python vigiechiro_api.py save-token`
  (le token est demandé sans s'afficher à l'écran) ;
- un **pipe** : `echo VOTRE_TOKEN | python vigiechiro_api.py save-token` ;
- la **variable d'environnement** `VIGIECHIRO_TOKEN`.

Passer le token en argument (`save-token VOTRE_TOKEN` ou `--token VOTRE_TOKEN`)
reste possible mais **déconseillé** : l'application affiche alors un
avertissement pour vous le rappeler.

## Données sensibles

Avant de partager une capture, un log ou un fichier d'exemple, masquez :

- les **noms de contrats / clients** ;
- les **numéros de sites** précis et **coordonnées GPS** des points d'écoute
  (information de conservation sensible).

## Signaler une vulnérabilité

Si vous découvrez une faille de sécurité, **n'ouvrez pas d'issue publique**.
Contactez le mainteneur en privé via son profil
[GitHub](https://github.com/kevin-guille) (ou son
[LinkedIn](https://fr.linkedin.com/in/kevin-guille-764b6a150)) en décrivant le
problème. Un correctif sera publié dès que possible.

## Bonnes pratiques utilisateur

- Gardez ChiroTool et ses dépendances à jour.
- Ne committez jamais `credentials.json`, `materiels.json`, `registry.db` ni vos
  fichiers de données — ils sont exclus par le `.gitignore`.
