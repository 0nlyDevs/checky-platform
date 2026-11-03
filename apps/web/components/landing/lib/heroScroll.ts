/**
 * Scroll state shared by the galaxy hero (DOM) and its WebGL scene.
 *
 * The hero is pinned for `pinLen` px. Over that run (`p` 0 → 1) the disc tilts
 * into 3D, its cards wind into a tunnel the camera flies through, then a torch
 * picks one card (the rumour reel) while the rest go dark and sends it to the
 * reel slot of the rumour section, which then rises around it.
 */
export const HERO_PHASE = {
  /** Copy leaves and the disc starts to tilt. */
  copyEnd: 0.16,
  tiltEnd: 0.3,
  /** Cards leave the disc for the tunnel walls (staggered by their journey). */
  tunnelAt: 0.2,
  tunnelEnd: 0.62,
  /** The torch beam sweeps in and settles on one card. */
  torchAt: 0.52,
  pickAt: 0.6,
  pickEnd: 0.82,
  /** Everything but the picked card is dark. */
  darkEnd: 0.9,
};

export const heroScroll = {
  /** Progress through the pin, 0 → 1. */
  p: 0,
  /**
   * Where the picked card lands: the reel slot of « La rumeur », in viewport
   * px. While that section is still rising this is the slot's final place.
   */
  slot: null as DOMRect | null,
};

export const smoothstep = (a: number, b: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};
