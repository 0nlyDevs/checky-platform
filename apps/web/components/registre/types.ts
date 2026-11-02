// Shapes of the registry, seal and figures API (apps/api/app/modules/registry.py, figures.py).

export type DiffOp = { op: "equal" | "insert" | "delete" | "replace"; a: string; b: string };
export type ChangedNumber = { kind: string; original: string | null; submitted: string | null };
export type MatchStatus = "authentic" | "modified" | "not_found" | "inconsistent" | "none";
export type Newsroom = { slug: string; name: string };

export type Communique = {
  id: string;
  issuer: string;
  number: string | null;
  issued_on: string | null;
  title: string;
  text: string;
  url: string | null;
  status: "original" | "fake_caught";
  is_demo: boolean;
  created_at: string;
  location: { name?: string; region?: string | null };
  own: boolean;
  newsroom: Newsroom | null;
  confirmations: number;
  confirmed: boolean;
  confirmed_by_us: boolean;
  sealed: { key_id: string; signature: string; sealed_at: string; url: string } | null;
  original_id: string | null;
  diff: DiffOp[];
  changed_numbers: ChangedNumber[];
  summary: string | null;
  fakes: number;
};

export type MatchResult = {
  status: MatchStatus;
  issuer: string | null;
  number: string | null;
  communique: {
    id: string;
    issuer: string;
    number: string | null;
    issued_on: string | null;
    title: string;
    text: string;
    url: string | null;
    is_demo: boolean;
    own: boolean;
    newsroom: Newsroom | null;
    confirmed: boolean;
    sealed: boolean;
    seal_url: string | null;
  } | null;
  diff: DiffOp[];
  changed_numbers: ChangedNumber[];
  summary: string;
};

export type SealResult = {
  sealed: { key_id: string; signature: string; sealed_at: string; url: string };
  payload: Record<string, string | null>;
  public_key: string;
  qr_svg: string;
  public: boolean;
};

export type SealKey = {
  key_id: string;
  issuer: string;
  public_key: string;
  created_at: string;
  revoked_at: string | null;
  seals: number;
};

export type PublicSeal = {
  id: string;
  alg: string;
  payload: Record<string, string | null>;
  message: string;
  signature: string;
  key_id: string;
  public_key: string;
  sealed_at: string;
  sealed_by: "issuer" | "newsroom";
  revoked_at: string | null;
  is_demo: boolean;
  newsroom: Newsroom;
  url: string;
  text: string;
};

export type OfficialEntry = {
  id: string;
  kind: "original" | "fake_caught";
  issuer: string;
  number: string | null;
  issued_on: string | null;
  title: string;
  text: string;
  url: string | null;
  is_demo: boolean;
  created_at: string;
  newsroom: Newsroom;
  confirmed: boolean;
  sealed: boolean;
  seal_url: string | null;
  fakes: number;
  original: { id: string; issuer: string; number: string | null; issued_on: string | null; title: string } | null;
  diff: DiffOp[];
  changed_numbers: ChangedNumber[];
  summary: string | null;
};

/** « 1er novembre 2026 » from YYYY-MM-DD (read as a calendar day, no time zone shift). */
export function frenchDay(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  const day = new Date(Date.UTC(y, m - 1, d));
  const text = day.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  return d === 1 ? text.replace(/^1 /, "1er ") : text;
}

/** « N° 2026-118 de JIRAMA » */
export function communiqueRef(c: { issuer: string; number: string | null }): string {
  return c.number ? `N° ${c.number} de ${c.issuer}` : c.issuer;
}
