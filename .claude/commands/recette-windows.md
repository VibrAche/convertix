---
description: Dérouler la recette Windows de Convertix et corriger les bugs trouvés
---
Lis CLAUDE.md (section « Recette Windows »). Ensuite :
1. Vérifie l'environnement (`python --version`, `.venv`), installe les dépendances si besoin, lance `python -m pytest -q`.
2. Pour chaque point de la checklist que tu peux tester toi-même (CLI, `--formats`, `--to`, `--install`, lecture du registre
   avec `reg query`), exécute-le et note le résultat.
3. Pour les points qui demandent une action d'Enzo (clic droit, raccourci, fenêtre), donne-lui une instruction courte,
   attends son retour, puis lis `%APPDATA%\Convertix\convertix.log`.
4. Corrige chaque bug trouvé (avec un test quand c'est possible), puis coche la case correspondante dans CLAUDE.md.
Termine par un résumé : ce qui marche, ce qui a été corrigé, ce qui reste.
