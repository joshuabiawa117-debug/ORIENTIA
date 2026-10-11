/* Fond de carte commun aux cartes d'OrientIA.
 *
 * L'adresse des tuiles vient des réglages (CARTE_TUILES_URL dans config/.env).
 * Mode économie de données : si le téléphone l'a activé, les tuiles (les images de la carte, assez lourdes)
 * ne sont chargées que lorsque l'élève le demande. Les marqueurs des écoles restent toujours visibles.
 */
window.ajouterFondDeCarte = function (carte, libelleBouton) {
    const reglages = JSON.parse(document.getElementById('tuilesCarte').textContent);
    // referrerPolicy : le fournisseur de tuiles doit savoir quel site les demande. Sans cela, OpenStreetMap
    // bloque les tuiles (« Access blocked ») dans les navigateurs qui masquent cette information, comme Brave.
    const fond = () => L.tileLayer(reglages.url, {
        attribution: reglages.attribution, maxZoom: 19, referrerPolicy: 'strict-origin-when-cross-origin',
    }).addTo(carte);

    const economie = navigator.connection && navigator.connection.saveData;
    if (!economie) {
        fond();
        return;
    }
    const Bouton = L.Control.extend({
        onAdd() {
            const bouton = L.DomUtil.create('button', 'btn-soft btn-sm-x bouton-fond-carte');
            bouton.type = 'button';
            bouton.innerHTML = '<i class="bi bi-map"></i> ';
            bouton.append(libelleBouton);
            L.DomEvent.disableClickPropagation(bouton);
            bouton.addEventListener('click', () => { fond(); this.remove(); });
            return bouton;
        },
    });
    new Bouton({ position: 'topright' }).addTo(carte);
};
