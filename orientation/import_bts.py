"""Extraction des programmes officiels de BTS depuis le PDF « Offre de formation BTS » du MINESUP."""
import re

from pypdf import PdfReader

DOMAINES = {
    'AGROPASTORAL': 'agropastoral',
    'EAU ET ENVIRONNEMENT': 'eau_environnement',
}

# Une ligne d'UE se termine par 5 ou 6 nombres (CM, TD, TP, TPE, total, crédits) : une colonne peut être vide
RE_UE = re.compile(r'^([A-Z]{2,4}\s?\d{3})\s+(.+?)\s+((?:\d+\s+){4,5}\d+)\s*$')
RE_CODE = re.compile(r'^([A-Z]{2,4}\s?\d{3})\s+(.*)$')
RE_NOMBRES_FIN = re.compile(r'^(.*?)\s*((?:\d+\s+){4,5}\d+)\s*$')


def nettoyer(texte):
    """Recolle les mots coupés par l'extraction PDF et normalise les espaces."""
    texte = texte.replace('’', "'").replace('', '-').replace('', '-')
    texte = re.sub(r'[ \t]+', ' ', texte)
    return texte.strip()


def lire_sommaire(pages):
    """Liste ordonnée de (domaine, famille, spécialité) lue dans le sommaire."""
    sommaire = next(p for p in pages if 'SOMMAIRE' in p)
    domaine = famille = None
    resultat = []
    for ligne in sommaire.splitlines():
        ligne = nettoyer(ligne)
        if ligne.startswith('DOMAINE'):
            domaine = ligne.split(':', 1)[1].strip()
        elif ligne.lower().startswith('filière'):
            famille = ligne.split(':', 1)[1].strip()
        elif '....' in ligne.replace(' ', '') and domaine and not ligne.startswith('AVANT'):
            nom = re.sub(r'[ .]*\d+$', '', ligne).strip(' .')
            resultat.append((domaine, famille, nom))
    return resultat


ACCENTS = {
    'elevage': 'élevage', 'metiers': 'métiers', 'vegetale': 'végétale', 'hydrogeologie': 'hydrogéologie',
    'forestiere': 'forestière', 'agroequipement': 'agroéquipement', 'meteorologie': 'météorologie',
}


def avec_accents(texte):
    """Rétablit les accents perdus dans les titres en majuscules du sommaire."""
    mots = []
    for mot in texte.split(' '):
        correct = ACCENTS.get(mot.lower())
        mots.append((correct.capitalize() if mot[:1].isupper() else correct) if correct else mot)
    return ' '.join(mots).replace("l'eau", "l'eau")


def nom_specialite(entete, nom_sommaire):
    """Nom écrit en minuscules accentuées juste avant la fiche, sinon celui du sommaire."""
    for candidat in reversed(re.findall(r'Sp[ée]cialit[ée]\s*:\s*(.+)', entete)):
        candidat = nettoyer(candidat)
        if candidat and not candidat.isupper():
            return candidat[0].upper() + candidat[1:]
    return avec_accents(nom_sommaire.capitalize())


def section(texte, debut, fin):
    """Texte entre deux titres (expressions régulières), ou chaîne vide."""
    m = re.search(debut + r'(.*?)' + fin, texte, flags=re.S | re.I)
    return m.group(1).strip() if m else ''


def lire_unites(organisation):
    """UE par semestre depuis la section « Organisation des enseignements »."""
    unites = []
    semestre = 0
    categorie = ''
    en_cours = None  # UE dont l'intitulé continue sur la ligne suivante

    for brute in organisation.splitlines():
        ligne = nettoyer(brute)
        if not ligne:
            continue
        m_sem = re.match(r'SEMESTRE\s*(\d)', ligne, flags=re.I)
        if m_sem:
            semestre = int(m_sem.group(1))
            continue
        if ligne.startswith('UE '):
            mot = ligne.split()[1].lower()
            categorie = ('fondamentale' if mot.startswith('fondament') else
                         'professionnelle' if mot.startswith('profession') else
                         'transversale' if mot.startswith('transvers') else '')
            continue

        m = RE_UE.match(ligne)
        if m:
            en_cours = None
            nombres = m.group(3).split()
            unites.append(dict(semestre=semestre, code=m.group(1).replace(' ', ''), intitule=m.group(2).strip(),
                               categorie=categorie, heures=int(nombres[-2]), credits=int(nombres[-1])))
            continue

        m_code = RE_CODE.match(ligne)
        if m_code:
            en_cours = dict(semestre=semestre, code=m_code.group(1).replace(' ', ''), intitule=m_code.group(2).strip(),
                            categorie=categorie)
            continue

        if en_cours:
            m_fin = RE_NOMBRES_FIN.match(ligne)
            if m_fin:
                suite = m_fin.group(1).strip()
                # L'extraction répète parfois la fin de l'intitulé : on ne l'ajoute qu'une fois
                if suite and suite not in en_cours['intitule']:
                    en_cours['intitule'] += ' ' + suite
                nombres = m_fin.group(2).split()
                en_cours.update(heures=int(nombres[-2]), credits=int(nombres[-1]))
                unites.append(en_cours)
                en_cours = None
            elif ligne not in en_cours['intitule']:
                en_cours['intitule'] += ' ' + ligne

    for u in unites:
        u['intitule'] = re.sub(r'\s+', ' ', u['intitule']).strip(' ,;')
    return unites


def extraire(chemin_pdf):
    """Renvoie la liste des spécialités avec objectif, débouchés et unités d'enseignement."""
    pages = [p.extract_text() or '' for p in PdfReader(chemin_pdf).pages]
    texte = '\n'.join(pages)
    sommaire = lire_sommaire(pages)

    # Début de chaque fiche : « FILIERE : ... Spécialité : ... 1. OBJECTIF DE LA FORMATION »
    debuts = [m.start() for m in re.finditer(r'1\.\s*OBJECTIFS? DE LA FORMATION', texte)]
    fiches = []
    for i, (domaine, famille, nom) in enumerate(sommaire):
        if i >= len(debuts):
            break
        bloc = texte[debuts[i]:debuts[i + 1] if i + 1 < len(debuts) else len(texte)]
        objectif = nettoyer(re.sub(r'\s+', ' ', section(bloc, r'OBJECTIFS? DE LA FORMATION', r'2\.\s*COMP')))
        debouches_bruts = section(bloc, r'3\.\s*D[EÉ]BOUCH[EÉ]S', r'4\.\s*ORGANISATION')
        debouches = [nettoyer(d).strip(' -;.') for d in re.split(r'\n\s*-\s*|;\s*\n', debouches_bruts)]
        debouches = [re.sub(r'\s+', ' ', d) for d in debouches if len(d) > 3 and 'Page' not in d]
        organisation = section(bloc, r'4\.\s*ORGANISATION DES ENSEIGNEMENTS', r'5\.\s*DESCRIPTIF')
        fiches.append(dict(
            nom=nom_specialite(texte[max(0, debuts[i] - 400):debuts[i]], nom),
            domaine=DOMAINES.get(domaine, 'autre'),
            famille=avec_accents(famille.capitalize()),
            objectif=objectif,
            debouches=debouches,
            unites=lire_unites(organisation),
        ))
    return fiches
