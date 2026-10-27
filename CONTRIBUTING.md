# Contribuer à Convertix

Merci de vouloir aider ! Toute aide est la bienvenue : signaler un bug, proposer une idée, corriger une faute ou ajouter un format.

## Signaler un bug ou proposer une idée

Ouvre une [issue](https://github.com/VibrAche/convertix/issues/new/choose) et remplis le formulaire.
Pour un bug, le **journal** de l'app aide énormément (Réglages → « Journal »).

## Proposer du code

1. Forke le dépôt et crée une branche : `git checkout -b mon-amelioration`
2. Installe l'environnement :
   ```bash
   python -m venv .venv && .venv\Scripts\activate      # Mac : source .venv/bin/activate
   pip install -r requirements.txt -r requirements-dev.txt
   ```
3. Fais ta modification, puis vérifie que tout passe : `python -m pytest -q`
4. Ouvre une Pull Request en expliquant ce que tu as changé et pourquoi.

## Les règles du projet

- **Ne jamais modifier ni écraser le fichier d'origine** : le résultat est toujours créé à côté.
- **Tout reste sur l'ordinateur** : aucune conversion ne doit passer par Internet.
- **Interface en français**, avec le tutoiement et des phrases courtes.
- **Aucun droit administrateur** nécessaire.
- **Un nouveau format = une règle + un fichier d'exemple** dans `tests/make_samples.py` (il est alors testé automatiquement).

La recette pour ajouter un format, l'architecture et la feuille de route sont dans [CLAUDE.md](CLAUDE.md).

## Licence

En contribuant, tu acceptes que ton code soit publié sous la licence du projet, [AGPL-3.0](LICENSE).
