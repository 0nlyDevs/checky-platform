"use client";

import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";
import type { RegionCount } from "@/components/rubrique/types";
import { t } from "@/lib/i18n/fr";

const v = t.rubrique.veille;

// SVG attributes cannot read CSS variables: the DESIGN.md values, written out. The tiles stay light
// in both themes, so ink and citron read on them either way.
const INK = "#171a18";
const CITRON = "#d7f45b";
const MADAGASCAR: [number, number] = [-19.2, 46.7];

/**
 * One circle per region, its area following what circulated there in the last 7 days, darker as
 * the share of high-risk dossiers grows. The selected region is the highlight (citron). Loaded
 * with `next/dynamic` and `ssr: false`: Leaflet needs the window.
 */
export default function VeilleMap({ regions, selected, onSelect }: { regions: RegionCount[]; selected: string | null; onSelect: (region: string | null) => void }) {
  const placed = regions.filter((r) => r.lat != null && r.lng != null && r.last_7d > 0);
  return (
    <MapContainer center={MADAGASCAR} zoom={5} minZoom={4} maxZoom={10} scrollWheelZoom={false} className="h-full w-full" attributionControl>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {placed.map((r) => {
        const on = r.region === selected;
        const risk = r.last_7d ? r.high_risk / r.last_7d : 0;
        return (
          <CircleMarker
            key={r.region}
            center={[r.lat as number, r.lng as number]}
            radius={7 + Math.sqrt(r.last_7d) * 5}
            pathOptions={{ color: INK, weight: on ? 3 : 1.5, fillColor: on ? CITRON : INK, fillOpacity: on ? 0.9 : 0.25 + 0.5 * risk }}
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
