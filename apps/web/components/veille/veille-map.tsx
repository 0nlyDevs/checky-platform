"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { RegionCount } from "@/components/rubrique/types";
import { t } from "@/lib/i18n/fr";

const v = t.rubrique.veille;

// SVG attributes cannot read CSS variables: the DESIGN.md ink, written out. The tiles stay light in
// both themes, so the ink reads on them either way; colour belongs to verdicts only.
const INK = "#0a0a0b";
const MADAGASCAR: [number, number] = [-19.2, 46.7];
// Where to look when a country has nothing placed yet (the map otherwise fits its circles).
const CENTRES: Record<string, [number, number, number]> = {
  madagascar: [-19.2, 46.7, 5],
  comores: [-11.9, 43.9, 8],
  maurice: [-20.3, 57.6, 9],
  seychelles: [-4.7, 55.5, 9],
  "la reunion": [-21.1, 55.5, 9],
  senegal: [14.5, -14.5, 6],
  "cote d'ivoire": [7.5, -5.5, 6],
  cameroun: [5.7, 12.4, 6],
  "republique democratique du congo": [-2.9, 23.6, 5],
  mali: [17.6, -4, 5],
  "burkina faso": [12.2, -1.6, 6],
  benin: [9.3, 2.3, 6],
  togo: [8.6, 0.9, 7],
  niger: [17.6, 8.1, 5],
  guinee: [9.9, -9.7, 6],
  gabon: [-0.8, 11.6, 6],
  kenya: [0.2, 37.9, 6],
  "afrique du sud": [-30.6, 22.9, 5],
  maroc: [31.8, -7.1, 5],
  tunisie: [34, 9.5, 6],
  france: [46.6, 2.4, 5],
  belgique: [50.6, 4.6, 7],
  canada: [56, -96, 3],
  haiti: [19, -72.7, 7],
};
const fold = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

/** Recentres when the country changes: fit its circles, else its centre, else the world. */
function Frame({ country, points }: { country: string; points: [number, number][] }) {
  const map = useMap();
  const key = `${country}|${points.length}`;
  useEffect(() => {
    if (fold(country) === "monde") {
      map.setView([5, 20], 2);
    } else if (points.length > 1) {
      map.fitBounds(points, { padding: [40, 40], maxZoom: 7 });
    } else if (points.length === 1) {
      map.setView(points[0], 6);
    } else {
      const c = CENTRES[fold(country)];
      if (c) map.setView([c[0], c[1]], c[2]);
      else map.setView([5, 20], 2);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recentre on a new country or new circles only
  }, [key, map]);
  return null;
}

/**
 * One circle per region, its area following what circulated there in the last 7 days, darker as
 * the share of high-risk dossiers grows. The selected region is filled and ringed in ink. Loaded
 * with `next/dynamic` and `ssr: false`: Leaflet needs the window.
 */
export default function VeilleMap({ regions, selected, onSelect, country = "Madagascar" }: { regions: RegionCount[]; selected: string | null; onSelect: (region: string | null) => void; country?: string }) {
  const placed = regions.filter((r) => r.lat != null && r.lng != null && r.last_7d > 0);
  return (
    <MapContainer center={MADAGASCAR} zoom={5} minZoom={2} maxZoom={10} scrollWheelZoom={false} className="h-full w-full" attributionControl>
      <Frame country={country} points={placed.map((r) => [r.lat as number, r.lng as number])} />
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {placed.map((r) => {
        const on = r.region === selected;
        const risk = r.last_7d ? r.high_risk / r.last_7d : 0;
        return (
          <CircleMarker
            key={r.region}
            center={[r.lat as number, r.lng as number]}
            radius={7 + Math.sqrt(r.last_7d) * 5}
            pathOptions={{ color: INK, weight: on ? 4 : 1.5, fillColor: INK, fillOpacity: on ? 0.85 : 0.2 + 0.45 * risk }}
            eventHandlers={{ click: () => onSelect(on ? null : r.region) }}
            bubblingMouseEvents={false}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{r.region}</strong>
              <br />
              {v.mapTooltip(r.last_24h, r.last_7d)}
              {r.high_risk > 0 && (
                <>
                  <br />
                  {v.highRisk} : {r.high_risk}
                </>
              )}
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
