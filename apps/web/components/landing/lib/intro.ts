/**
 * Master clock of the galaxy hero intro. One time base for the wordmark, the
 * copy reveal, the scrim, the arm lines and the card wave, so a skip
 * (wheel, click, key) fast-forwards all of them together.
 */
export const INTRO = {
  /** Letters start sliding out from behind the first letter (it fades in at 0). */
  wordAt: 0.35,
  /** Whole word formation; the first letter glides to its slot over this window. */
  wordDur: 0.85,
  /** Arm lines, ticks and circle fade in. */
  instrAt: 0.7,
  /** Copy stack reveal. */
  copyAt: 1.05,
  /** Cards start rolling out from the centre along their arms. */
  cardsAt: 1,
  /** Timeline speed while the visitor skips. */
  ffScale: 4,
};

export const introClock = { t: 0, scale: 1, done: false };

export function fastForwardIntro() {
  if (!introClock.done && introClock.scale < INTRO.ffScale) introClock.scale = INTRO.ffScale;
}
