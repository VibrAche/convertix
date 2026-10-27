---
description: Ajouter une nouvelle conversion à Convertix
argument-hint: "<entrée> vers <sortie>, ex. : SVG vers PNG"
---
Ajoute la conversion suivante : $ARGUMENTS

Suis la recette « Ajouter un format » de CLAUDE.md : règle `reg.add(...)` dans le bon module de `convertix/converters/`,
fichier d'exemple dans `tests/make_samples.py`, dépendance dans `requirements.txt` ET `packaging/convertix.spec` si
nécessaire (privilégie une solution hors ligne, légère, multiplateforme). Lance `python -m pytest -q`, puis
`python run.py --formats <fichier d'exemple>` pour montrer le résultat. Mets à jour le tableau des moteurs dans CLAUDE.md.
