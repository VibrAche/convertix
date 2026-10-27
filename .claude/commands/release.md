---
description: Publier une nouvelle version de Convertix (installeur Windows + Mac via GitHub Actions)
argument-hint: "<version>, ex. : 0.2.0"
---
Publie la version $ARGUMENTS :
1. `python -m pytest -q` doit être vert.
2. Mets `__version__ = "$ARGUMENTS"` dans `convertix/__init__.py`.
3. Commit « Version $ARGUMENTS », puis `git tag v$ARGUMENTS` et `git push && git push --tags`.
4. Suis le workflow avec `gh run watch` ; en cas d'échec, lis les logs (`gh run view --log-failed`) et corrige.
5. Donne à Enzo le lien de la Release (`gh release view v$ARGUMENTS --web` ou l'URL).
