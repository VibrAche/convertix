# CLAUDE.md — consignes pour Claude Code

Ce fichier est lu automatiquement par Claude Code. Il décrit le projet, ses règles
et la feuille de route. **Réponds toujours en français** à Enzo (le propriétaire du projet).

## Le projet en une phrase

**Convertix** est une petite application de bureau (Windows d'abord, Mac ensuite) qui
convertit n'importe quel fichier en un autre format : on sélectionne un fichier dans
l'Explorateur, on tape **Ctrl+Alt+C** (ou clic droit → « Convertir avec Convertix »),
une fenêtre propose les formats possibles, on clique, c'est converti à côté de l'original.

Cas d'usage n°1 : les photos iPhone transférées sur PC (**DNG / ProRAW, HEIC, MOV**)
à convertir en JPEG / PNG / MP4. Viennent ensuite les PDF, Word, Excel, PowerPoint,
audio, vidéo, et le traitement par lot (plusieurs fichiers ou un dossier entier).

## Dépôt GitHub

Dépôt **public** : https://github.com/VibrAche/convertix (le README est la vitrine : rester simple et en français).
Le build des installeurs se fait par GitHub Actions (onglet Actions → dernier run → Artifacts ;
Releases publiées automatiquement sur un tag `v*`). Ne jamais committer de photos perso ni d'e-mail.
Captures et GIF du README : `docs/` (régénérés à partir du vrai code de l'éventail sur un faux bureau).

## Commandes utiles

```bash
# installation (une fois)
python -m venv .venv && .venv\Scripts\activate          # Windows
pip install -r requirements.txt -r requirements-dev.txt

python -m pytest -q                       # tests du moteur (≈10 s)
python run.py --verbose                   # lance l'app (icône + fenêtre)
python run.py --convert C:\chemin\photo.dng   # fenêtre de conversion pour ce fichier
python run.py --to jpg --out out photo.dng    # conversion sans interface
python run.py --formats fichier.pdf           # formats proposés pour un fichier
python run.py --install / --uninstall         # clic droit + Envoyer vers + démarrage auto
pyinstaller packaging/convertix.spec --noconfirm   # build → dist/Convertix/
python packaging/make_icon.py             # régénère assets/icon.(png|ico|icns)
```

Scripts PowerShell prêts à l'emploi : `scripts\dev_windows.ps1` (lancer en dev),
`scripts\build_windows.ps1` (construire l'exe + l'installeur localement).

Journal de l'app : `%APPDATA%\Convertix\convertix.log` (Mac : `~/Library/Application Support/Convertix/`).
Paramètres : `settings.json` dans le même dossier. **Toujours lire le journal en premier en cas de bug.**

## Architecture

```
run.py                         point d'entrée (dev + PyInstaller)
convertix/
  app.py                       CLI, instance unique (QLocalServer + QLockFile), icône tray, raccourci
  engine.py                    registre « extension → format cible », convert(), merge_to_pdf(), collect_files()
  settings.py                  paramètres JSON + journal
  proc.py                      lancement ffmpeg / LibreOffice sans console, annulable
  converters/
    images.py                  Pillow + pillow-heif (HEIC) + rawpy (DNG/RAW) ; EXIF, orientation, transparence
    documents.py               Office via COM (Windows) > LibreOffice > Python pur (PyMuPDF, pdf2docx, openpyxl…)
    media.py                   ffmpeg (binaire fourni par imageio-ffmpeg)
  gui/
    fan.py                     éventail de bulles en verre autour de la souris : choix du format → progression → ✓
                               (capture floutée de l'écran derrière = effet « liquid glass »)
    worker.py                  thread de conversion (QThread)
    settings_dialog.py         Réglages (clic droit sur l'icône) : couleur, thème, raccourci, qualité, sortie…
                               chaque changement est enregistré tout de suite
    glass.py                   fenêtre sans cadre au fond dégradé « verre » (utilisée par les Réglages)
    widgets.py                 interrupteur iOS et pastille de couleur dessinés à la main
    style.py                   feuille de style, couleur d'accent et thème (auto / clair / sombre)
  platform_integration/
    __init__.py                façade multiplateforme (seule API utilisée par l'app)
    windows.py                 registre HKCU, Envoyer vers, sélection Explorateur (COM + repli presse-papiers), RegisterHotKey
    macos.py                   Finder (AppleScript), pynput, Action rapide, LaunchAgent — NON TESTÉ
packaging/                     spec PyInstaller, installeur Inno Setup, icônes
.github/workflows/build.yml    build Windows (.exe installeur + zip portable) et Mac (.dmg), Release sur tag v*
tests/                         make_samples.py (génère des fichiers), test_conversions.py
```

### Flux d'un clic droit sur 10 fichiers
Windows lance 10 processus `Convertix.exe --convert "<fichier>"`. Chacun tente de se connecter
au serveur local de l'instance principale (l'icône) et lui envoie son fichier, puis s'arrête.
L'instance principale attend 350 ms (`COLLECT_MS`) pour regrouper tous les fichiers dans **une seule**
fenêtre. Si aucune instance ne tourne, le premier processus qui obtient `instance.lock` devient principal.

### Flux du raccourci clavier
`RegisterHotKey` (Windows) → `Controller.on_hotkey` → `get_selected_files()` :
1. fenêtre Explorateur au premier plan → COM `Shell.Application` (`Document.SelectedItems()`) ;
   avec les onglets de Windows 11, on départage par le titre de la fenêtre ;
2. sinon (Bureau, cas ambigu) → on simule Ctrl+C, on lit `CF_HDROP` du presse-papiers, puis on le restaure.

## Règles du projet (à respecter dans toute modification)

1. **Ne jamais modifier ni écraser l'original.** Les sorties passent par `Output.file()` / `unique_path()`
   → `photo (1).jpg` si `photo.jpg` existe. Un fichier à moitié écrit est supprimé en cas d'erreur.
2. **Interface et messages d'erreur en français**, tutoiement, phrases courtes.
   Les erreurs destinées à l'utilisateur sont des `ConversionError("message lisible")`.
3. **Aucun droit administrateur** : tout dans `HKEY_CURRENT_USER`, installation dans `%LOCALAPPDATA%\Programs`.
4. **Hors ligne et privé** : aucune conversion ne passe par Internet. Ne jamais ajouter d'API web de conversion.
5. Le moteur (`engine.py`, `converters/`) **n'importe jamais Qt** : il doit rester utilisable en CLI et testable.
6. Imports lourds **à l'intérieur des fonctions** (rawpy, fitz, pdf2docx, win32com…) pour garder un démarrage rapide
   des processus lancés par le clic droit.
7. Toute nouvelle conversion = une règle `reg.add(...)` + un test (le test `test_convert_all` couvre
   automatiquement chaque format proposé pour chaque fichier d'exemple ; ajouter un exemple dans `make_samples.py`).
8. Garder `requirements.txt` et `packaging/convertix.spec` (hiddenimports / datas) synchronisés.
   **Pas de PyMuPDF 2.x** (embarque onnxruntime, +200 Mo).
9. Commits en français, petits et descriptifs. Bumper `convertix/__init__.py:__version__` avant un tag `vX.Y.Z`.

## Ajouter un format (recette)

1. Choisir le module (`images.py`, `documents.py`, `media.py`) ou en créer un et l'appeler dans `engine.registry()`.
2. Écrire `def _ma_conversion(src, target, out, opts) -> list[Path]` :
   `dest = out.file(target.ext)` → écrire → `return [dest]`. Appeler `opts.check_cancel()` dans les boucles longues.
3. `reg.add({".ext_entree"}, Target("cle", "Libellé", ".ext", "Groupe"), _ma_conversion, available=..., priority=...)`.
   `available` = test rapide de présence du moteur ; `priority` départage plusieurs moteurs (Office 10 > LibreOffice 5 > Python 1).
4. Ajouter un fichier d'exemple dans `tests/make_samples.py`, lancer `pytest`.

## Moteurs selon le type de fichier

| Entrée | Sorties | Moteur |
|---|---|---|
| DNG / RAW (CR2, NEF, ARW…) | JPEG, PNG, WebP, HEIC, AVIF, TIFF, BMP, GIF, ICO, PDF | rawpy (repli : aperçu JPEG intégré, puis Pillow) |
| HEIC / HEIF | idem | pillow-heif |
| JPEG, PNG, WebP, TIFF, GIF, BMP, AVIF… | idem | Pillow |
| SVG | idem (rendu 2048 px) + PDF vectoriel | PyMuPDF |
| PDF | Word, PNG/JPEG/SVG (1 par page), TXT | pdf2docx, PyMuPDF |
| EPUB, MOBI, FB2, XPS, CBZ | PDF, TXT, PNG/JPEG (1 par page) | PyMuPDF |
| Images + PDF (plusieurs) | **un seul PDF fusionné** (A4) | PyMuPDF |
| Word / ODT / RTF / TXT | PDF, DOCX, ODT, RTF, TXT | Word (COM) > LibreOffice ; DOCX→TXT en Python |
| Excel / ODS | PDF, XLSX, ODS, CSV | Excel (COM) > LibreOffice ; XLSX→CSV (toutes feuilles, `;`) en Python |
| CSV | XLSX (Python, nombres FR « 12,50 » reconnus), PDF, ODS | openpyxl / Office / LibreOffice |
| PowerPoint / ODP | PDF, PPTX, ODP, PNG/JPEG (1 par diapo) | PowerPoint (COM) > LibreOffice |
| Vidéo (MOV iPhone, MP4, MKV…) | MP4 H.264, MOV, MKV, WebM, GIF animé, + extraction audio | ffmpeg |
| Audio | MP3, M4A, WAV, FLAC, OGG, Opus | ffmpeg |

Sans Office **ni** LibreOffice installés, les conversions Word/Excel/PowerPoint → PDF ne sont pas proposées
(la fenêtre ne les affiche simplement pas). Piste : proposer d'installer LibreOffice depuis les Paramètres.

## État actuel (v0.1.0)

- ✅ Moteur testé sous Linux (75 conversions, frozen build PyInstaller OK).
- ⚠️ **Jamais lancé sur Windows ni sur Mac** : le code Windows (registre, COM, RegisterHotKey, presse-papiers)
  a été écrit sans pouvoir être exécuté. **Première mission : faire la recette Windows ci-dessous et corriger.**
- ⚠️ Aucun vrai DNG d'iPhone testé (seulement un DNG synthétique). Les ProRAW récents (iPhone 15/16, DNG 1.7
  compressé JPEG XL) peuvent ne pas être lus par LibRaw → repli automatique sur l'aperçu intégré. À vérifier.

## Recette Windows (checklist à dérouler avec Enzo)

- [x] `pip install -r requirements.txt -r requirements-dev.txt` puis `pytest -q` → tout vert
- [ ] `python run.py --verbose` → icône dans la zone de notification + bulle « Prêt ! »
- [ ] Sélectionner une photo HEIC et un DNG d'iPhone, Ctrl+Alt+C → éventail → JPG : rotation, couleurs, EXIF (date) conservés
- [ ] Éventail : effet verre visible (fond flouté), texte lisible sur fond clair et sombre, Échap / clic à côté referme
- [ ] Clic droit sur l'icône → Réglages : changer la couleur et le thème s'applique tout de suite
- [ ] `python run.py --install` → clic droit sur un .dng : « Convertir avec Convertix » (Windows 11 : dans « Afficher plus d'options »)
- [ ] Clic droit sur **10 fichiers** à la fois → **une seule** fenêtre avec les 10 fichiers
- [ ] « Envoyer vers > Convertix » sur une sélection mixte (images + PDF)
- [ ] Clic droit sur un dossier → « Convertir le contenu » → tous les fichiers du dossier (sauf `Convertis/`)
- [ ] **Ctrl+Alt+C** dans l'Explorateur (1 onglet, puis plusieurs onglets), sur le Bureau, avec rien de sélectionné
- [ ] Vérifier que le presse-papiers est intact après le raccourci sur le Bureau
- [ ] Ctrl+Alt+C quand une autre app utilise déjà ce raccourci → notification claire
- [ ] Word/Excel/PowerPoint → PDF avec Office installé (et sans Office : entrées absentes, pas de plantage)
- [ ] MOV iPhone (HEVC, HDR) → MP4 : lecture OK dans le lecteur Windows (couleurs HDR potentiellement délavées)
- [ ] Annuler une longue conversion vidéo → pas de fichier partiel
- [ ] Paramètres : changer le raccourci, le mode de sortie « sous-dossier Convertis », démarrage auto
- [ ] Build CI : installer `Convertix-Setup-x.y.z.exe`, redémarrer, vérifier le démarrage auto + clic droit, désinstaller proprement

## Feuille de route (par priorité)

1. **Stabiliser Windows** (recette ci-dessus), corriger les bugs trouvés.
2. Notification Windows native avec bouton « Ouvrir » ; barre de progression ffmpeg réelle (lire `-progress pipe:1`).
3. Conversions en parallèle pour les images (ThreadPool, ~4 workers) — garder Office/ffmpeg séquentiels.
4. Options par format : redimensionner (ex. « 2048 px max »), supprimer le GPS des photos, PNG→JPEG fond de couleur.
5. MOV iPhone → MP4 « rapide » sans réencodage (`-c copy`) quand le codec est déjà H.264, et tonemapping HDR→SDR.
6. Menu clic droit **de premier niveau** sous Windows 11 (nécessite un `IExplorerCommand` + paquet MSIX signé : gros chantier).
7. **Mac** : tester `macos.py` (Action rapide Finder, pynput + autorisation Accessibilité, LaunchAgent), signer/notariser le .dmg.
8. Réduire la taille : pdf2docx tire OpenCV (~150 Mo) ; envisager Word COM pour PDF→DOCX quand Office est présent
   et rendre pdf2docx optionnel.
9. Mise à jour automatique (vérifier la dernière Release GitHub au démarrage).

## Publication

1. Mettre à jour `__version__` dans `convertix/__init__.py`.
2. `git commit` puis `git tag v0.1.0 && git push --tags`.
3. GitHub Actions construit et publie : `Convertix-Setup-0.2.0.exe`, `Convertix-Portable-Windows-0.2.0.zip`,
   `Convertix-0.2.0-mac-apple-silicon.dmg` et `Convertix-0.2.0-mac-intel.dmg` dans l'onglet **Releases**.

Note : les exécutables ne sont pas signés → Windows SmartScreen affiche « Windows a protégé votre ordinateur »
(→ « Informations complémentaires » → « Exécuter quand même ») et macOS demande clic droit → Ouvrir.
