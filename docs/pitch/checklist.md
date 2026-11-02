# Checklist · du gel au pitch

Qui : {{nom}} tient cette liste et coche. Une case non cochée à 7 h 30 mercredi est un problème, pas une surprise.

## Lundi 2 novembre, 8 h 30 (juste après la vidéo du besoin)

- [ ] Noter mot pour mot la phrase du besoin et une citation de la vidéo → `docs/pitch/deck/content.js` (`need.title`, `need.quote`).
- [ ] Décider en 10 minutes ce qu'on garde, renomme ou retire de l'app (grille, tableau, sources, Vérifier, carte, public).
- [ ] Choisir **la** rumeur qu'on suivra du début à la fin (ouverture, démo, fin) et la remplacer partout : `deck/content.js` et `video/scenes.json`.
- [ ] Désigner qui parle et qui tient le clavier (`team.speaker`, `team.driver`).

## Mardi 3 novembre, 18 h → 20 h (le gel est à 20 h, pas une minute de plus)

- [ ] 18 h 00 : plus de nouvelle fonctionnalité. Corrections seulement.
- [ ] Déployé et vérifié depuis un téléphone en données mobiles : inscription, démo, le parcours de la démo.
- [ ] `npm run third-party` → `THIRD_PARTY.md` à jour, commité (règlement, article 6).
- [ ] `node docs/pitch/deck/build.js` → **0 trou**. `grep -n "{{" docs/pitch/deck/content.js docs/pitch/video/scenes.json` ne renvoie rien.
- [ ] Deck importé dans Google Slides, partagé aux quatre, ouvert sur le téléphone de l'orateur (plan C si l'ordinateur meurt).
- [ ] Export PDF du deck sur une clé USB (plan D : l'ordinateur de l'IFM).
- [ ] Vidéo de secours filmée **sur l'app déployée** : `uv run --with playwright python -I scripts/pitch_video.py --base-url https://…` → `video/out/demo.mp4` copié sur l'ordinateur de l'orateur et sur la clé.
- [ ] Trois répétitions chronométrées. Objectif 2 min 45 : la salle fait perdre 15 secondes.
- [ ] Partage de connexion testé sur deux téléphones (le réseau de l'IFM n'est pas garanti).
- [ ] Dormir.

## Mercredi 4 novembre

### À la maison, 6 h 45

- [ ] Ouvrir `/api/v1/health` de l'API déployée (réveille Render, environ 1 minute) et la page Paramètres (réveille Neon).
- [ ] Paramètres : base, stockage et au moins un fournisseur d'IA en vert.

### À l'IFM, 20 minutes avant le passage

- [ ] Réveiller l'API et la base à nouveau (`/api/v1/health`, Paramètres) : elles se rendorment après 15 minutes.
- [ ] Paramètres → **Réinitialiser les données** de démonstration (admin).
- [ ] Onglets ouverts dans cet ordre, rien d'autre : 1 · Google Slides en mode présentation ; 2 · l'app sur la première page de la démo ; 3 · `demo.mp4` en pause à 0:00 ; 4 · `/verifies`.
- [ ] Mode « ne pas déranger » sur l'ordinateur et le téléphone de l'orateur. Luminosité au maximum. Chargeur branché.
- [ ] Partage de connexion actif, Wi-Fi de la salle oublié si lent.
- [ ] Tester la sortie vidéo du projecteur avec la slide 1 (couleurs manila et encre, pas de bord coupé) et le son si la vidéo doit en avoir.
- [ ] Une bouteille d'eau pour l'orateur.

### Pendant les 3 minutes

- Le chrono démarre à la première phrase. Le clavier avance les slides ; l'orateur ne touche à rien.
- Démo en direct seulement si la slide 1 s'est affichée sans attente et que Paramètres était vert 20 minutes avant. Sinon, vidéo commentée. On ne « tente » pas.
- Si quelque chose casse en direct : « Je vous le montre sur la vidéo », et le clavier lance `demo.mp4`. Pas d'excuse, pas de rechargement.
- Finir sur la slide « FANILO » et rester dessus pour les questions.

### Après

- [ ] Noter les questions du jury (pour le README et pour la suite).
- [ ] Remercier les organisateurs, récupérer la clé USB.
