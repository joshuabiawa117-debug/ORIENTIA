"""Découpage des documents en passages d'environ 500 caractères (remplace langchain, trop lourd pour ce seul usage)."""

SEPARATEURS = ("\n\n", "\n", ". ", " ")


def _morceler(texte, taille, separateurs):
    """Coupe d'abord aux paragraphes, puis aux lignes, aux phrases, aux mots ; en dernier recours, au caractère."""
    if len(texte) <= taille:
        return [texte]
    if not separateurs:
        return [texte[i:i + taille] for i in range(0, len(texte), taille)]
    separateur, plus_fins = separateurs[0], separateurs[1:]
    if separateur not in texte:
        return _morceler(texte, taille, plus_fins)

    blocs, courant = [], ""
    for partie in texte.split(separateur):
        candidat = f"{courant}{separateur}{partie}" if courant else partie
        if len(candidat) <= taille:
            courant = candidat
            continue
        if courant:
            blocs.append(courant)
        if len(partie) > taille:
            blocs.extend(_morceler(partie, taille, plus_fins))
            courant = ""
        else:
            courant = partie
    if courant:
        blocs.append(courant)
    return blocs


def decouper(texte, taille=500, chevauchement=50):
    """Liste de passages ; chacun reprend la fin du précédent (≈ `chevauchement` caractères) pour garder le fil."""
    blocs = [b.strip() for b in _morceler(texte, taille, SEPARATEURS) if b.strip()]
    passages = []
    for i, bloc in enumerate(blocs):
        if i and chevauchement:
            fin_precedente = blocs[i - 1][-chevauchement:]
            # On commence la reprise au début d'un mot
            espace = fin_precedente.find(" ")
            reprise = fin_precedente[espace + 1:] if espace != -1 else ""
            if reprise:
                bloc = f"{reprise} {bloc}"
        passages.append(bloc)
    return passages
