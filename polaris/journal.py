# -*- coding: utf-8 -*-
"""Journal d'execution.

Chaque anomalie est ecrite plutot que passee sous silence. Un titre dont le
cours manque, une devise introuvable, un etat financier absent : si ca ne
remonte pas, le classement bouge sans que personne sache pourquoi.
"""

from __future__ import annotations

import datetime as dt

_LIGNES: list[str] = []


def note(message: str) -> None:
    horodatage = dt.datetime.now().strftime("%H:%M:%S")
    ligne = f"[{horodatage}] {message}"
    _LIGNES.append(ligne)
    print(ligne, flush=True)


def lignes() -> list[str]:
    return list(_LIGNES)


def vider() -> None:
    _LIGNES.clear()
