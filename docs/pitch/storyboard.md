# Storyboard · la démo en 60 secondes

Ce que la vidéo montre, scène par scène. Les étapes exactes vivent dans `video/scenes.json` ; ce fichier est la version qu'on relit à quatre. La vidéo est **muette** : l'orateur la commente en direct (slide 5). Si on veut une version narrée pour la publier ensuite, on enregistre la voix par-dessus dans n'importe quel éditeur.

Format : 1920 × 1080, 30 images/s. Chaque scène = un carton de chapitre (1,6 s, monde « dossier ») puis l'app filmée avec un curseur visible et un sous-titre sur une fiche. Total visé : 60 à 75 secondes, jamais plus de 90.

## Les scènes (version actuelle, à remplacer lundi)

| # | Chapitre | Ce qu'on voit | Ce que dit l'orateur pendant ce temps | Durée |
| --- | --- | --- | --- | --- |
| 0 | Titre | « Chaque rumeur a son dossier. » | (le besoin en une phrase) | 2 s |
| 1 | La grille du jour | `/affirmations` : les blocs du 23 h 47 → maintenant, le curseur survole deux rumeurs | « Voilà le desk à 6 h du matin : tout ce qui circule, depuis quand. » | 8 s |
| 2 | Le dossier | On ouvre « le prix du riz » : origine, heure, sources jointes, analyse de l'IA citation par citation | « Chaque rumeur a son dossier. Les preuves, et ce que l'IA en lit. » | 12 s |
| 3 | Un journaliste signe | Le verdict suggéré « trompeur », le bouton Confirmer | « L'IA propose. Une personne signe. Jamais l'inverse. » | 10 s |
| 4 | Vérifier | `/verifier` : une question tapée, la réponse arrive avec ses citations | « Une question à toutes les sources de la rédaction, et la réponse cite. » | 15 s |
| 5 | Pour le public | `/verifies` : un message collé, l'assistant répond à partir des verdicts publiés | « Et le public peut demander si c'est déjà vérifié, sans compte. » | 12 s |
| 6 | Fin | FANILO · adresse · équipe | « Chaque rumeur a son dossier. » | 2,5 s |

## Lundi : réécrire les scènes

1. Trois chapitres maximum pour la vraie démo, dans l'ordre où le jury doit comprendre : **le problème vu de l'écran → le geste qui le règle → ce qui en sort**.
2. Une scène = une page, un geste, un résultat visible. Pas de menu, pas de réglages, pas de connexion à l'écran.
3. Le sous-titre dit ce que l'orateur ne dira pas (un détail), jamais la même phrase que lui.
4. Chaque scène a une sortie visible : un verdict, une carte, une réponse, un badge « en direct » chez un collègue.
5. Si une étape dépend de l'IA (réponse, analyse), la mettre en `wait_for` avec 90 s : le tournage attend, le montage coupe. Et vérifier que `AI_CACHE=true` pour qu'une reprise donne la même réponse.

## Règles de tournage

- Données de démo uniquement (bouton Paramètres → Réinitialiser) : toute rumeur à l'écran est fictive et étiquetée.
- Aucun nom réel, aucun numéro, aucune clé, aucune adresse avec un jeton dans l'URL.
- Interface en français ; le curseur est le seul « acteur ».
- Filmer sur l'app déployée mardi soir (`--base-url`) : c'est la copie de secours.
- Garder les scènes séparées (`video/out/scenes/`) : on en refait une sans tout refaire (`--only id`).

## Si on veut la version « bubble » (narrée, pour publier)

La recette de la vidéo WebCup tient en quatre choses, toutes compatibles avec ce qui sort d'ici : un personnage qui raconte à gauche, une étiquette par chapitre (ici, les cartons), les écrans dans un cadre, un sous-titre sous chaque plan (ici, les fiches). Ajouter la voix et le personnage dans l'éditeur habituel de l'équipe, à partir de `demo.mp4` ou des scènes séparées. Durée raisonnable pour une publication : 2 à 3 minutes, pas 8.
