"""Lanceur : `python run.py` (développement) et point d'entrée PyInstaller."""
import multiprocessing
import sys

from convertix.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
