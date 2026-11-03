# Storyboard · une rumeur, de 23 h 47 au verdict

La vidéo suit **la même rumeur** que l'ouverture du pitch, de son arrivée jusqu'au public. Les étapes exactes vivent dans `video/scenes.json` ; ce fichier est la version qu'on relit à quatre. La vidéo est **muette** : l'orateur la commente en direct (slide « Démo »). Si on veut une version narrée pour la publier, on enregistre la voix par-dessus dans n'importe quel éditeur.

Format : 1920 × 1080, 30 images/s. Chaque scène = un carton de chapitre (1,6 s, monde « dossier ») puis l'app filmée avec un curseur visible et un sous-titre sur une fiche. Total visé : 60 à 75 secondes.

## Les scènes

| # | Chapitre | Ce qu'on voit | Ce que dit l'orateur | Durée |
| --- | --- | --- | --- | --- |
| 0 | Pièce 1 | « Une vidéo arrive sur WhatsApp. » | (rien : le carton parle) | 2,6 s |
| 1 | La rumeur arrive | La grille du desk : le curseur s'arrête sur la vidéo d'Analakely, puis ouvre son dossier (heure, origine, preuves) | « Voilà la vidéo de 23 h 47 dans la grille du desk. Elle devient un dossier, avec ses preuves. » | 15 s |
| 2 | L'IA lit, le journaliste signe | L'analyse des sources, citation par citation ; « Examiner », puis « Confirmer » ; la carte est prête | « L'IA a lu les preuves et propose un verdict. Le journaliste vérifie, et il signe. » | 20 s |
| 3 | Le public la retrouve | `/verdicts` sans compte : on colle le message reçu, l'assistant retrouve le dossier et cite le verdict | « Quelqu'un reçoit la même vidéo. Il demande si c'est vérifié : la réponse cite le dossier. » | 15 s |
| 4 | Le matin | « Vérifié. » · adresse · équipe | (rien) | 2,6 s |

Avant de filmer, le script prépare l'histoire par l'API : il retrouve la rumeur, la remet « en cours » sans verdict et lance l'analyse de l'IA ; avant la scène 3, il la publie (ce que le journaliste ferait en fin de vérification). Le verdict proposé est celui que le modèle renvoie vraiment : les sous-titres ne le nomment jamais.

## Changer de rumeur

1. Choisir une rumeur du vrai sujet qui a des preuves jointes dans les données de démonstration (ou en ajouter).
2. La remplacer partout en même temps : `deck/content.js` (couverture, notes, chapitres) et `video/scenes.json` (`find`, sélecteurs `text=…`, message collé dans la scène 3).
3. Trois chapitres, pas plus, dans l'ordre où le jury comprend : **elle arrive → on la vérifie → elle sort**.
4. Une scène = une page, un geste, un résultat visible. Pas de menu, pas de réglages, pas de connexion à l'écran.
5. Le sous-titre dit ce que l'orateur ne dira pas (un détail), jamais la même phrase que lui.

## Règles de tournage

- Données de démo uniquement : toute rumeur à l'écran est fictive et étiquetée.
- Aucun nom réel, aucun numéro, aucune clé, aucune adresse avec un jeton dans l'URL.
- Interface en français ; le curseur est le seul « acteur ».
- Filmer sur l'app déployée mardi soir (`--base-url`) : c'est la copie de secours.
- Garder les scènes séparées (`video/out/scenes/`) : on en refait une sans tout refaire (`--only id`).

## Si on veut une version narrée (pour publier)

Une étiquette par chapitre (les cartons), les écrans dans un cadre, un sous-titre sous chaque plan (les fiches) : il suffit d'ajouter la voix dans l'éditeur habituel de l'équipe, à partir de `demo.mp4` ou des scènes séparées. Durée raisonnable pour une publication : 2 à 3 minutes.
