// The 23 regions of Madagascar, as the API's gazetteer names them (apps/api/app/core/places.py).
export const MG_REGIONS = [
  "Alaotra-Mangoro",
  "Amoron'i Mania",
  "Analamanga",
  "Analanjirofo",
  "Androy",
  "Anosy",
  "Atsimo-Andrefana",
  "Atsimo-Atsinanana",
  "Atsinanana",
  "Betsiboka",
  "Boeny",
  "Bongolava",
  "Diana",
  "Fitovinany",
  "Haute Matsiatra",
  "Ihorombe",
  "Itasy",
  "Melaky",
  "Menabe",
  "Sava",
  "Sofia",
  "Vakinankaratra",
  "Vatovavy",
] as const;

// Time zones a newsroom here is likely to pick; any IANA name is accepted by the API.
export const TIMEZONES = ["Indian/Antananarivo", "Indian/Comoro", "Indian/Mayotte", "Indian/Reunion", "Indian/Mauritius", "Africa/Nairobi", "Europe/Paris", "UTC"] as const;

export type NewsroomSettings = {
  double_signature: boolean;
  ai_enabled: boolean;
  beats: string[];
  timezone: string;
  country: string;
  region: string | null;
};
export type WorkspaceDetail = { id: string; name: string; slug: string; is_public: boolean; settings: NewsroomSettings };
