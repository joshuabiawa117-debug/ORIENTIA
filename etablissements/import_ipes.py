"""Lecture de la liste officielle des IPES (instituts privés d'enseignement supérieur autorisés par le MINESUP)."""
import re
import unicodedata

from pypdf import PdfReader

# Ville (sans accents, en minuscules) → (nom affiché, latitude, longitude) : positions approximatives du centre-ville
VILLES = {
    'yaounde': ('Yaoundé', 3.8480, 11.5021), 'douala': ('Douala', 4.0511, 9.7679), 'obala': ('Obala', 4.1680, 11.5330),
    'mbalmayo': ('Mbalmayo', 3.5170, 11.5000), 'ombessa': ('Ombessa', 4.6000, 11.2500), 'buea': ('Buea', 4.1527, 9.2410),
    'kumba': ('Kumba', 4.6360, 9.4460), 'limbe': ('Limbe', 4.0160, 9.2060), 'tiko': ('Tiko', 4.0750, 9.3600),
    'bamenda': ('Bamenda', 5.9631, 10.1591), 'kumbo': ('Kumbo', 6.2040, 10.6760), 'bafoussam': ('Bafoussam', 5.4781, 10.4176),
    'dschang': ('Dschang', 5.4440, 10.0530), 'bangangte': ('Bangangté', 5.1410, 10.5240), 'foumban': ('Foumban', 5.7270, 10.9000),
    'mbouda': ('Mbouda', 5.6260, 10.2540), 'bafang': ('Bafang', 5.1570, 10.1800), 'ngaoundere': ('Ngaoundéré', 7.3167, 13.5833),
    'garoua': ('Garoua', 9.3014, 13.3977), 'maroua': ('Maroua', 10.5956, 14.3247), 'bertoua': ('Bertoua', 4.5772, 13.6846),
    'ebolowa': ('Ebolowa', 2.9000, 11.1500), 'kribi': ('Kribi', 2.9400, 9.9100), 'sangmelima': ('Sangmélima', 2.9330, 11.9830),
    'edea': ('Edéa', 3.8000, 10.1330), 'nkongsamba': ('Nkongsamba', 4.9540, 9.9400),
}

# En-têtes de région du document → nom de région utilisé dans OrientIA (l'ordre compte : du plus précis au plus général)
REGIONS = [
    ('extreme', 'Extrême-Nord'), ('nord-ouest', 'Nord-Ouest'), ('sud-ouest', 'Sud-Ouest'), ('adamaoua', 'Adamaoua'),
    ('centre', 'Centre'), ('littoral', 'Littoral'), ('ouest', 'Ouest'), ('est', 'Est'), ('nord', 'Nord'), ('sud', 'Sud'),
]

RE_ENTREE = re.compile(r"^(\d{1,3})\s+(\S.*?)\s*$")
# Lignes de l'en-tête officiel répété sur certaines pages
RE_IGNOREE = re.compile(r"^(-+|\d+|REPUBLI.*|Paix-Travail.*|Peace-Work.*|MINIST.*|LISTE DES.*|AUTORISEES.*)$", re.I)


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn").lower()


def region_de(entete):
    texte = sans_accents(entete)
    for cle, region in REGIONS:
        if re.search(rf"\b{cle}\b", texte):
            return region
    return None


def ville_dans(nom):
    """Ville citée dans le nom de l'institut (ex. « Institut Saint Jean de Yaoundé »), sinon None."""
    texte = sans_accents(nom)
    for cle, ville in VILLES.items():
        if re.search(rf"\b{cle}\b", texte):
            return ville
    return None


def lire_lignes(lignes):
    """Liste de (région, nom) à partir des lignes de texte du document."""
    instituts, region, courant = [], None, None

    def terminer():
        if courant and region:
            nom = re.sub(r"\s+", " ", courant).strip().rstrip(".")
            instituts.append((region, nom.replace("’", "'")))

    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        if sans_accents(ligne).startswith("region"):
            terminer()
            courant, region = None, region_de(ligne[len("Région"):])
            continue
        if RE_IGNOREE.match(ligne):
            continue
        entree = RE_ENTREE.match(ligne)
        if entree:
            terminer()
            courant = entree.group(2)
        elif courant:
            # Nom coupé sur plusieurs lignes : « Institut ... Développement » + « Durable (ISSTMADD) »
            courant += " " + ligne
    terminer()
    return instituts


def lire_pdf(chemin):
    texte = "\n".join(page.extract_text() or "" for page in PdfReader(chemin).pages)
    return lire_lignes(texte.splitlines())
