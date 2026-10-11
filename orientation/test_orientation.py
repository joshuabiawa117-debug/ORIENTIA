"""Questions du test d'orientation : chaque réponse rapporte des points à un ou plusieurs domaines."""
from django.utils.translation import gettext_lazy as _

QUESTIONS = [
    {
        "texte": _("Pendant ton temps libre, tu préfères…"),
        "reponses": [
            (_("Bricoler, démonter ou réparer des objets"), {"genie": 2}),
            (_("Être sur un ordinateur ou ton téléphone à explorer des applis"), {"informatique": 2}),
            (_("Lire, écrire ou regarder des débats"), {"communication": 2, "droit_administration": 1}),
            (_("Être dehors, au champ ou avec des animaux"), {"agropastoral": 2, "eau_environnement": 1}),
        ],
    },
    {
        "texte": _("Ta matière préférée au lycée, c'est plutôt…"),
        "reponses": [
            (_("Les mathématiques"), {"sciences": 2, "informatique": 1, "genie": 1}),
            (_("La physique-chimie"), {"genie": 2, "sciences": 1}),
            (_("Les SVT / la biologie"), {"sante": 2, "agropastoral": 1}),
            (_("Le français, l'histoire ou les langues"), {"communication": 2, "enseignement": 1}),
        ],
    },
    {
        "texte": _("Un ami a un problème. Ton premier réflexe ?"),
        "reponses": [
            (_("L'écouter et le rassurer"), {"sante": 1, "enseignement": 2}),
            (_("Chercher une solution concrète et efficace"), {"genie": 1, "gestion": 2}),
            (_("Lui expliquer ses droits et les règles"), {"droit_administration": 2}),
            (_("Chercher l'info sur internet pour l'aider"), {"informatique": 1, "sciences": 1}),
        ],
    },
    {
        "texte": _("Dans un travail de groupe, tu es celui ou celle qui…"),
        "reponses": [
            (_("Organise et répartit les tâches"), {"gestion": 2, "droit_administration": 1}),
            (_("Présente le travail devant la classe"), {"communication": 2, "enseignement": 1}),
            (_("Fait les calculs et vérifie les résultats"), {"sciences": 2, "genie": 1}),
            (_("Prépare les tableaux, schémas et documents sur ordinateur"), {"informatique": 2}),
        ],
    },
    {
        "texte": _("Quel métier te fait le plus rêver ?"),
        "reponses": [
            (_("Médecin, pharmacien·ne ou infirmier·ère"), {"sante": 3}),
            (_("Ingénieur·e qui construit des routes ou des barrages"), {"genie": 3}),
            (_("Développeur·se ou expert·e en cybersécurité"), {"informatique": 3}),
            (_("Diplomate, magistrat·e ou administrateur·trice"), {"droit_administration": 3}),
        ],
    },
    {
        "texte": _("Et parmi ceux-là ?"),
        "reponses": [
            (_("Journaliste ou communicant·e"), {"communication": 3}),
            (_("Chef·fe d'entreprise ou banquier·ère"), {"gestion": 3}),
            (_("Agronome ou éleveur·se moderne"), {"agropastoral": 3}),
            (_("Enseignant·e ou chercheur·se"), {"enseignement": 2, "sciences": 2}),
        ],
    },
    {
        "texte": _("L'environnement et le climat, pour toi…"),
        "reponses": [
            (_("C'est essentiel, j'aimerais travailler pour les protéger"), {"eau_environnement": 3}),
            (_("C'est important pour mieux cultiver et nourrir le pays"), {"agropastoral": 2, "eau_environnement": 1}),
            (_("Ça m'intéresse surtout à travers la science"), {"sciences": 2}),
            (_("Pas spécialement mon sujet"), {}),
        ],
    },
    {
        "texte": _("Tu préfères travailler…"),
        "reponses": [
            (_("Dans un bureau, avec des dossiers et des chiffres"), {"gestion": 2, "droit_administration": 1}),
            (_("Sur le terrain, en plein air"), {"agropastoral": 1, "eau_environnement": 2, "genie": 1}),
            (_("Dans un laboratoire ou un hôpital"), {"sante": 2, "sciences": 1}),
            (_("Face à un public, une classe ou une caméra"), {"communication": 2, "enseignement": 2}),
        ],
    },
    {
        "texte": _("Résoudre une équation difficile, ça te…"),
        "reponses": [
            (_("Passionne, j'adore les défis logiques"), {"sciences": 2, "informatique": 2}),
            (_("Plaît si ça sert à quelque chose de concret"), {"genie": 2}),
            (_("Va, sans plus"), {"gestion": 1}),
            (_("Fatigue, je préfère les mots aux chiffres"), {"communication": 2, "droit_administration": 1}),
        ],
    },
    {
        "texte": _("Quel projet aimerais-tu mener ?"),
        "reponses": [
            (_("Créer une application utile pour les Camerounais"), {"informatique": 3}),
            (_("Ouvrir ma propre entreprise ou mon commerce"), {"gestion": 3}),
            (_("Monter une ferme moderne ou une pisciculture"), {"agropastoral": 3}),
            (_("Améliorer l'accès à l'eau potable dans les villages"), {"eau_environnement": 3}),
        ],
    },
    {
        "texte": _("Tu te sens à l'aise pour…"),
        "reponses": [
            (_("Expliquer quelque chose à quelqu'un qui n'a pas compris"), {"enseignement": 3}),
            (_("Convaincre et négocier"), {"gestion": 2, "communication": 1}),
            (_("Argumenter et défendre une position"), {"droit_administration": 2, "communication": 1}),
            (_("Soigner ou prendre soin des autres"), {"sante": 3}),
        ],
    },
    {
        "texte": _("Les études longues (5 ans ou plus), c'est…"),
        "reponses": [
            (_("Pas un problème si c'est pour un beau métier"), {"sante": 1, "genie": 1, "sciences": 1}),
            (_("Bien, mais je veux aussi pratiquer rapidement"), {"informatique": 1, "gestion": 1}),
            (_("Je préfère une formation courte et pro (BTS…)"), {"agropastoral": 1, "eau_environnement": 1, "gestion": 1}),
            (_("Je ne sais pas encore"), {}),
        ],
    },
    {
        "texte": _("Quelle actualité lis-tu en premier ?"),
        "reponses": [
            (_("Les nouvelles technologies"), {"informatique": 2, "genie": 1}),
            (_("La politique et les relations internationales"), {"droit_administration": 2, "communication": 1}),
            (_("L'économie et les affaires"), {"gestion": 2}),
            (_("La santé et les découvertes scientifiques"), {"sante": 1, "sciences": 2}),
        ],
    },
    {
        "texte": _("Ce que tu veux avant tout dans ton futur métier…"),
        "reponses": [
            (_("Être utile à ma communauté"), {"sante": 1, "enseignement": 1, "eau_environnement": 1}),
            (_("Bien gagner ma vie"), {"gestion": 1, "informatique": 1, "genie": 1}),
            (_("Créer, innover"), {"informatique": 1, "communication": 1, "genie": 1}),
            (_("Avoir un poste stable dans l'administration"), {"droit_administration": 2, "enseignement": 1}),
        ],
    },
    {
        "texte": _("Un exposé à préparer : tu choisis comme sujet…"),
        "reponses": [
            (_("Le fonctionnement d'un moteur ou d'une centrale électrique"), {"genie": 3}),
            (_("La place des femmes dans les médias"), {"communication": 3}),
            (_("Le paludisme et comment le soigner"), {"sante": 3}),
            (_("L'histoire des mathématiques"), {"sciences": 2, "enseignement": 1}),
        ],
    },
    {
        "texte": _("Si tu gagnais un stage d'été, tu irais…"),
        "reponses": [
            (_("Dans une startup du numérique à Douala ou Yaoundé"), {"informatique": 2, "gestion": 1}),
            (_("Dans un chantier ou une usine"), {"genie": 2}),
            (_("Dans une station agricole ou forestière"), {"agropastoral": 2, "eau_environnement": 1}),
            (_("Dans un ministère ou une ambassade"), {"droit_administration": 2}),
        ],
    },
]

# Explication courte de chaque domaine, affichée dans les résultats
DESCRIPTIONS = {
    'agropastoral': _("Tu as la fibre de la terre et du vivant : agriculture, élevage, pisciculture… un secteur clé pour le Cameroun."),
    'eau_environnement': _("Tu veux protéger les ressources naturelles : eau, forêts, climat, assainissement."),
    'informatique': _("Tu es attiré·e par le numérique : développement, réseaux, télécoms, données."),
    'genie': _("Tu aimes comprendre comment les choses fonctionnent et les construire : génie civil, électrique, mécanique."),
    'sante': _("Prendre soin des autres te motive : médecine, pharmacie, soins infirmiers, laboratoires."),
    'gestion': _("Tu as l'esprit d'entreprise : gestion, commerce, finance, comptabilité."),
    'droit_administration': _("Les règles, la justice et le service public t'intéressent : droit, administration, diplomatie."),
    'communication': _("Tu as le goût des mots et des idées : journalisme, communication, langues, lettres."),
    'enseignement': _("Transmettre te plaît : enseignement général ou technique, formation."),
    'sciences': _("Tu as un esprit scientifique : mathématiques, physique, chimie, recherche."),
}


def calculer_scores(choix):
    """Transforme les réponses (index de réponse par question) en pourcentages par domaine.

    Le pourcentage compare les points obtenus au maximum possible pour chaque domaine,
    pour ne pas avantager les domaines qui apparaissent dans plus de questions.
    """
    obtenus, maximum = {}, {}
    for question, index in zip(QUESTIONS, choix):
        meilleurs = {}
        for _, points in question["reponses"]:
            for domaine, valeur in points.items():
                meilleurs[domaine] = max(meilleurs.get(domaine, 0), valeur)
        for domaine, valeur in meilleurs.items():
            maximum[domaine] = maximum.get(domaine, 0) + valeur
        if index is not None and 0 <= index < len(question["reponses"]):
            for domaine, valeur in question["reponses"][index][1].items():
                obtenus[domaine] = obtenus.get(domaine, 0) + valeur
    return {d: round(100 * obtenus.get(d, 0) / maximum[d]) for d in maximum}
