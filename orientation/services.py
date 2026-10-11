"""Recherche des écoles les plus proches de l'élève qui proposent les filières qui l'intéressent."""
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.utils.translation import gettext as _

from etablissements.models import Etablissement

from .models import Filiere

# Chef-lieu de chaque région (latitude, longitude) : position par défaut si l'élève n'a pas partagé la sienne
CHEFS_LIEUX = {
    'Adamaoua': ('Ngaoundéré', 7.3167, 13.5833),
    'Centre': ('Yaoundé', 3.8480, 11.5021),
    'Est': ('Bertoua', 4.5772, 13.6846),
    'Extrême-Nord': ('Maroua', 10.5956, 14.3247),
    'Littoral': ('Douala', 4.0511, 9.7679),
    'Nord': ('Garoua', 9.3014, 13.3977),
    'Nord-Ouest': ('Bamenda', 5.9631, 10.1591),
    'Ouest': ('Bafoussam', 5.4781, 10.4176),
    'Sud': ('Ebolowa', 2.9000, 11.1500),
    'Sud-Ouest': ('Buea', 4.1527, 9.2410),
}

# Centres d'intérêt de l'accueil progressif → domaines de filières
INTERETS_VERS_DOMAINES = {
    'mathématiques': 'sciences', 'informatique': 'informatique', 'physique-chimie': 'sciences',
    'biologie': 'sante', 'santé / médecine': 'sante', 'agriculture': 'agropastoral',
    'génie civil': 'genie', 'économie / gestion': 'gestion', 'commerce': 'gestion', 'droit': 'droit_administration',
    'langues': 'communication', 'lettres': 'communication', 'communication': 'communication', 'arts': 'communication',
}

# Mots du projet d'études → domaines
MOTS_PROJET = {
    'ingénieur': 'genie', 'informatique': 'informatique', 'santé': 'sante', 'médecin': 'sante',
    'enseign': 'enseignement', 'commerce': 'gestion', 'gestion': 'gestion', 'droit': 'droit_administration',
    'journalis': 'communication', 'agricul': 'agropastoral', 'environnement': 'eau_environnement',
}


def position_par_defaut(profil):
    """(Point, libellé) à partir de la région du profil, ou (None, None)."""
    if profil and profil.region in CHEFS_LIEUX:
        ville, lat, lon = CHEFS_LIEUX[profil.region]
        return Point(lon, lat, srid=4326), _("%(ville)s (région %(region)s)") % {"ville": ville, "region": profil.region}
    return None, None


def domaines_du_profil(profil):
    """Domaines de filières qui correspondent aux goûts et au projet de l'élève."""
    if not profil:
        return []
    domaines = []
    # 1. Les 3 domaines les mieux classés au dernier test d'orientation
    dernier_test = profil.utilisateur.resultats_test.first()
    if dernier_test:
        domaines.extend(dernier_test.domaines_principaux(3))
    # 2. Les centres d'intérêt choisis à l'inscription
    for interet in profil.centres_interet.split(','):
        domaine = INTERETS_VERS_DOMAINES.get(interet.strip().lower())
        if domaine and domaine not in domaines:
            domaines.append(domaine)
    projet = f"{profil.projet_etudes} {profil.ecole_souhaitee}".lower()
    for mot, domaine in MOTS_PROJET.items():
        if mot in projet and domaine not in domaines:
            domaines.append(domaine)
    return domaines


def ecoles_proches(point, filiere=None, domaines=None, limite=None):
    """Établissements triés par distance, filtrés sur une filière ou une liste de domaines."""
    ecoles = Etablissement.objects.all()
    if filiere:
        ecoles = ecoles.filter(filieres=filiere)
    elif domaines:
        ecoles = ecoles.filter(filieres__domaine__in=domaines).distinct()
    if point is not None:
        ecoles = ecoles.annotate(distance=Distance('localisation', point)).order_by('distance')
    else:
        ecoles = ecoles.order_by('nom')
    ecoles = ecoles.prefetch_related('filieres')
    return list(ecoles[:limite] if limite else ecoles)


def resume_pour_orientia(profil, limite=5):
    """Texte ajouté au prompt d'OrientIA : les écoles proches dans les domaines de l'élève."""
    point, lieu = position_par_defaut(profil)
    domaines = domaines_du_profil(profil)
    if point is None or not domaines:
        return ""
    ecoles = ecoles_proches(point, domaines=domaines, limite=limite)
    if not ecoles:
        return ""
    noms_domaines = dict(Filiere.DOMAINES)
    lignes = []
    for e in ecoles:
        filieres = ", ".join(f.nom for f in e.filieres.all() if f.domaine in domaines)
        lignes.append(f"- {e.nom} : à {e.distance.km:.0f} km ({filieres})")
    return (f"Écoles les plus proches de l'élève (depuis {lieu}) dans ses domaines "
            f"({', '.join(str(noms_domaines[d]) for d in domaines)}) — propose-les si c'est pertinent :\n"
            + "\n".join(lignes) + "\n\n")
