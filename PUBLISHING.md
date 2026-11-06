# Publier craftkit

Le même programme part sur deux registres, gratuitement : `craftkit` sur PyPI, `craftkit-cli` sur npm (npm refuse `craftkit`, trop proche du
paquet `craft-kit` qui existe déjà) :

| Registre | Installation | Contenu |
|----------|--------------|---------|
| PyPI | `pipx install craftkit` · `uv tool install craftkit` · `uvx craftkit` | le paquet Python (wheel + sources) |
| npm  | `npm install -g craftkit-cli` · `npx craftkit-cli` | les mêmes fichiers Python + un lanceur Node (`bin/launch.js`) qui utilise le Python 3.9+ de la machine |

Commandes installées : `craft`, `craftkit`, `craft-new`, `craft-run`.

## Les accès (une seule fois)

Les jetons et mots de passe restent sur la machine : on les saisit dans son propre terminal, jamais
dans une conversation ni dans un fichier du projet.

**npm**
1. Créer un compte sur https://www.npmjs.com/signup et activer la double authentification
   (Account → Two-Factor Authentication).
2. Dans un terminal : `npm login` (ouvre le navigateur). Vérifier : `npm whoami`.
3. Au moment de publier, npm demande un code à 6 chiffres (ou une validation dans le navigateur).

**PyPI**
1. Créer un compte sur https://pypi.org/account/register/ et activer la double authentification
   (obligatoire).
2. Account settings → API tokens → Add API token, portée **Entire account** (le projet n'existe pas
   encore ; après la première publication, le remplacer par un jeton limité au projet `craftkit`).
3. Le mettre dans `~/.pypirc`, lisible par soi seul :
   ```ini
   [pypi]
   username = __token__
   password = pypi-…le jeton…
   ```
   puis `chmod 600 ~/.pypirc`.

## Publier une version

```sh
sh scripts/release-check.sh                     # construit et vérifie tout, ne publie rien
uvx twine upload dist/craftkit-*.tar.gz dist/craftkit-*.whl
npm publish dist/npm/craftkit-cli-*.tgz --access public   # --otp=123456 si demandé
```

Vérifier ensuite depuis un autre dossier : `uvx craftkit --version` et `npx craftkit-cli@latest --version`.

## Version suivante

Changer le numéro aux trois endroits (le script refuse s'ils diffèrent) : `pyproject.toml`,
`package.json`, `craft_kit/__init__.py`. Un numéro publié ne peut jamais être republié, ni sur PyPI
ni sur npm : une erreur se corrige par une nouvelle version.

Plus tard, avec un dépôt GitHub public : la publication peut partir d'un tag par GitHub Actions
(« trusted publishing » sur PyPI, provenance sur npm), sans jeton stocké nulle part.
