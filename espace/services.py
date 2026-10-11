"""Calculs de l'espace élève : moyennes, matières à réviser et propositions d'emploi du temps."""
from collections import defaultdict
from datetime import time
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from orientation.models import UniteEnseignement

from .models import Creneau, Note, Parcours

# Grille affichée : de 7 h à 21 h
HEURE_DEBUT_GRILLE = 7 * 60
HEURE_FIN_GRILLE = 21 * 60
PAUSE = 15  # minutes entre deux séances

MATIERES_PAR_DEFAUT = ["Mathématiques", "Physique-Chimie", "Français", "Anglais", "Culture générale"]


def minutes(t):
    return t.hour * 60 + t.minute


def heure(m):
    return time(m // 60, m % 60)


def parcours_de(user):
    parcours, _cree = Parcours.objects.get_or_create(utilisateur=user)
    return parcours


# ---------- Notes et moyennes ----------

def moyenne_ponderee(notes):
    total = sum(n.coefficient for n in notes)
    if not total:
        return None
    return sum(n.valeur * n.coefficient for n in notes) / total


def bilan_notes(user):
    """Moyenne par matière et par semestre, crédits validés (matière ≥ 10/20).

    La moyenne du semestre pondère chaque matière par ses crédits officiels (1 si la matière est libre).
    """
    par_semestre = defaultdict(lambda: defaultdict(list))
    for note in Note.objects.filter(utilisateur=user).select_related('unite'):
        par_semestre[note.semestre][note.matiere].append(note)

    bilan = []
    for semestre in sorted(par_semestre):
        matieres = []
        for nom, notes in sorted(par_semestre[semestre].items()):
            unite = next((n.unite for n in notes if n.unite), None)
            moyenne = moyenne_ponderee(notes)
            matieres.append({
                'nom': nom,
                'moyenne': moyenne,
                'credits': unite.credits if unite and unite.credits else None,
                'validee': moyenne is not None and moyenne >= 10,
                'nb_notes': len(notes),
            })
        poids = [(m['moyenne'], Decimal(m['credits'] or 1)) for m in matieres if m['moyenne'] is not None]
        total_poids = sum(p for _m, p in poids)
        bilan.append({
            'semestre': semestre,
            'matieres': matieres,
            'moyenne': sum(m * p for m, p in poids) / total_poids if total_poids else None,
            'credits_valides': sum(m['credits'] or 0 for m in matieres if m['validee']),
            'credits_total': sum(m['credits'] or 0 for m in matieres),
        })
    return bilan


# ---------- Matières à réviser ----------

def matieres_a_reviser(user):
    """Liste de (matière, poids) : plus le poids est grand, plus la matière reçoit de séances.

    Étudiant inscrit : les matières officielles de son semestre, pondérées par leurs crédits.
    Bachelier : les matières de ses notes et de son emploi du temps, ou des matières générales.
    Une matière avec une moyenne sous 10/20 reçoit un bonus : c'est là qu'il faut travailler.
    """
    parcours = parcours_de(user)
    poids = {}
    if parcours.statut == 'etudiant' and parcours.filiere_id and parcours.semestre:
        for ue in UniteEnseignement.objects.filter(filiere_id=parcours.filiere_id, semestre=parcours.semestre):
            if 'stage' not in ue.intitule.lower():
                poids[ue.intitule] = float(ue.credits or 2)
    if not poids:
        noms = list(Note.objects.filter(utilisateur=user).values_list('matiere', flat=True).distinct())
        noms += [c.intitule for c in Creneau.objects.filter(utilisateur=user, type_creneau='cours') if c.intitule]
        for nom in noms or MATIERES_PAR_DEFAUT:
            poids.setdefault(nom, 3.0)

    # Bonus pour les matières faibles
    for semestre in bilan_notes(user):
        for m in semestre['matieres']:
            if m['nom'] in poids and m['moyenne'] is not None and m['moyenne'] < 10:
                poids[m['nom']] += 3
    return sorted(poids.items(), key=lambda x: -x[1])


# ---------- Propositions d'emploi du temps ----------

FORMULES = [
    {
        'cle': 'equilibree', 'nom': _('Équilibrée'), 'icone': 'bi-yin-yang',
        'description': _("Des séances d'une heure réparties sur la semaine, sans surcharger tes journées."),
        'duree': 60, 'max_par_jour': 2, 'objectif_minutes': 8 * 60, 'dimanche': True,
    },
    {
        'cle': 'intensive', 'nom': _('Intensive'), 'icone': 'bi-lightning-charge',
        'description': _("Pour les périodes d'examens ou de concours : des séances longues et plus nombreuses."),
        'duree': 90, 'max_par_jour': 3, 'objectif_minutes': 15 * 60, 'dimanche': True,
    },
    {
        'cle': 'legere', 'nom': _('Légère'), 'icone': 'bi-feather',
        'description': _("Une séance courte par jour pour garder le rythme, avec le dimanche libre."),
        'duree': 45, 'max_par_jour': 1, 'objectif_minutes': 4 * 60, 'dimanche': False,
    },
]


def plages_libres(user):
    """Pour chaque jour, les intervalles (début, fin) en minutes où l'élève est disponible et n'a pas cours."""
    creneaux = list(Creneau.objects.filter(utilisateur=user))
    libres = {}
    for jour in range(7):
        dispos = sorted((minutes(c.debut), minutes(c.fin)) for c in creneaux if c.jour == jour and c.type_creneau == 'dispo')
        cours = sorted((minutes(c.debut), minutes(c.fin)) for c in creneaux if c.jour == jour and c.type_creneau == 'cours')
        intervalles = []
        for debut, fin in dispos:
            morceaux = [(debut, fin)]
            # On retire les heures de cours qui chevauchent la disponibilité
            for c_debut, c_fin in cours:
                nouveaux = []
                for d, f in morceaux:
                    if c_fin <= d or c_debut >= f:
                        nouveaux.append((d, f))
                    else:
                        if c_debut > d:
                            nouveaux.append((d, c_debut))
                        if c_fin < f:
                            nouveaux.append((c_fin, f))
                morceaux = nouveaux
            intervalles += morceaux
        libres[jour] = sorted(intervalles)
    return libres


def repartir_matieres(matieres, nombre):
    """Répartit `nombre` séances entre les matières, au prorata de leur poids, en les alternant."""
    if not matieres or nombre <= 0:
        return []
    total = sum(p for _m, p in matieres)
    quotas = {m: max(1, round(nombre * p / total)) for m, p in matieres}
    # Ajuster pour tomber exactement sur `nombre` (on retire d'abord aux matières les moins prioritaires)
    ordre = [m for m, _p in matieres]
    while sum(quotas.values()) > nombre:
        for m in reversed(ordre):
            if quotas[m] > 0 and sum(quotas.values()) > nombre:
                quotas[m] -= 1
    i = 0
    while sum(quotas.values()) < nombre:
        quotas[ordre[i % len(ordre)]] += 1
        i += 1
    # Alterner : A B C A B A ... plutôt que A A A B B C
    sequence = []
    while any(quotas.values()):
        for m in ordre:
            if quotas[m]:
                sequence.append(m)
                quotas[m] -= 1
    return sequence


def proposer_emplois_du_temps(user):
    """Construit une proposition par formule (équilibrée, intensive, légère) dans les plages libres."""
    libres = plages_libres(user)
    matieres = matieres_a_reviser(user)
    propositions = []
    for formule in FORMULES:
        places = []  # (jour, debut, fin) des séances possibles
        for jour in range(7):
            if jour == 6 and not formule['dimanche']:
                continue
            du_jour = []
            for debut, fin in libres[jour]:
                t = debut
                while t + formule['duree'] <= fin and len(du_jour) < formule['max_par_jour']:
                    du_jour.append((jour, t, t + formule['duree']))
                    t += formule['duree'] + PAUSE
            places += du_jour
        # Répartir les séances sur toute la semaine plutôt que de remplir les premiers jours
        nombre = min(len(places), max(1, formule['objectif_minutes'] // formule['duree']))
        if len(places) > nombre:
            pas = len(places) / nombre
            places = [places[int(k * pas)] for k in range(nombre)]
        sequence = repartir_matieres(matieres, len(places))
        seances = [
            {'jour': jour, 'debut': heure(d), 'fin': heure(f), 'matiere': matiere}
            for (jour, d, f), matiere in zip(places, sequence)
        ]
        propositions.append({
            **formule,
            'seances': seances,
            'total_heures': round(sum(f - d for _j, d, f in places) / 60, 1),
        })
    return propositions


def positionner(elements):
    """Ajoute à chaque élément sa position (en %) dans la grille hebdomadaire 7 h – 21 h."""
    amplitude = HEURE_FIN_GRILLE - HEURE_DEBUT_GRILLE
    resultat = []
    for e in elements:
        debut = max(minutes(e['debut']), HEURE_DEBUT_GRILLE)
        fin = min(minutes(e['fin']), HEURE_FIN_GRILLE)
        if fin <= debut:
            continue
        resultat.append({
            **e,
            'haut': round(100 * (debut - HEURE_DEBUT_GRILLE) / amplitude, 3),
            'hauteur': round(100 * (fin - debut) / amplitude, 3),
        })
    return resultat
