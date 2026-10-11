{% load static %}/* Service worker d'OrientIA : le site reste consultable avec une connexion instable ou coupée.
 *
 * - Les fichiers du site (CSS, JS, polices, logo) sont gardés en mémoire.
 * - Les pages consultées (fiches filières, concours, écoles, communauté, espace étudiant) sont gardées
 *   et réaffichées hors connexion. Les messages privés et le chat ne sont jamais gardés.
 * - À la déconnexion, les pages gardées sont effacées (téléphone partagé).
 */
const VERSION = '{{ version }}';
const DEV = {{ debug|yesno:"true,false" }};
const CACHE_STATIQUE = `orientia-statique-${VERSION}`;
const CACHE_PAGES = 'orientia-pages';
const PAGE_HORS_LIGNE = '{% url "hors_ligne" %}';

const A_PRECHARGER = [
    PAGE_HORS_LIGNE,
    '{% static "css/style.css" %}',
    '{% static "vendor/bootstrap/bootstrap.min.css" %}',
    '{% static "vendor/bootstrap/bootstrap.bundle.min.js" %}',
    '{% static "vendor/bootstrap-icons/bootstrap-icons.min.css" %}',
    '{% static "vendor/bootstrap-icons/fonts/bootstrap-icons.woff2" %}',
    '{% static "vendor/geist/geist.css" %}',
    '{% static "vendor/geist/geist-latin.woff2" %}',
    '{% static "img/favicon.svg" %}',
    '{% static "img/favicon-192.png" %}',
];

// Pages qui peuvent être gardées pour être relues hors connexion
const PAGES_A_GARDER = [
    /^\/$/, /^\/filieres\//, /^\/concours\/$/, /^\/annales\/$/, /^\/etablissements\/$/, /^\/ecoles-pour-toi\/$/,
    /^\/communaute\/(\d+\/)?$/, /^\/confidentialite\/$/, /^\/conditions\/$/, /^\/dashboard\/$/,
    /^\/mon-espace\/(ma-filiere|emploi-du-temps|suivi)\/$/,
];

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE_STATIQUE).then((cache) => cache.addAll(A_PRECHARGER)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    // Supprime les fichiers d'une ancienne version du site
    event.waitUntil(
        caches.keys()
            .then((noms) => Promise.all(noms.filter((n) => n.startsWith('orientia-statique-') && n !== CACHE_STATIQUE).map((n) => caches.delete(n))))
            .then(() => self.clients.claim())
    );
});

async function reseauPuisCache(requete, nomCache, garder) {
    try {
        const reponse = await fetch(requete);
        if (garder && reponse.ok && reponse.type === 'basic') {
            const cache = await caches.open(nomCache);
            cache.put(requete, reponse.clone());
        }
        return reponse;
    } catch (erreur) {
        const enCache = await caches.match(requete);
        if (enCache) return enCache;
        if (requete.mode === 'navigate') return caches.match(PAGE_HORS_LIGNE);
        throw erreur;
    }
}

async function cachePuisReseau(requete) {
    const enCache = await caches.match(requete);
    if (enCache) return enCache;
    return reseauPuisCache(requete, CACHE_STATIQUE, true);
}

self.addEventListener('fetch', (event) => {
    const requete = event.request;
    const url = new URL(requete.url);
    if (requete.method !== 'GET' || url.origin !== self.location.origin) return;

    if (url.pathname === '/deconnexion/') {
        event.waitUntil(caches.delete(CACHE_PAGES));
        return;
    }
    if (url.pathname.startsWith('/static/')) {
        // En développement, on prend toujours la dernière version des fichiers modifiés
        event.respondWith(DEV ? reseauPuisCache(requete, CACHE_STATIQUE, true) : cachePuisReseau(requete));
        return;
    }
    if (requete.mode === 'navigate') {
        const garder = PAGES_A_GARDER.some((motif) => motif.test(url.pathname));
        event.respondWith(reseauPuisCache(requete, CACHE_PAGES, garder));
    }
});
