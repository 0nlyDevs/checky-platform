"use client";

import "leaflet/dist/leaflet.css";
import { createLeafletContext, LeafletContext, type LeafletContextInterface } from "@react-leaflet/core";
import { Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { CircleMarker, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { RegionCount } from "@/components/rubrique/types";
import { t } from "@/lib/i18n/live";

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
 * The map's container. react-leaflet's `MapContainer` removes its map when its effects are cleaned up
 * and never builds a new one, but Next keeps a visited page alive and hidden (`<Activity>`): leaving
 * Veille cleans the effects up, coming back runs them again on the removed map and the page crashes
 * (« Map container is being reused », `_leaflet_pos`). Here the map survives while the page is only
 * hidden (its node stays in the document) and is removed once the node really leaves it; coming back
 * just re-measures it.
 */
function LiveMap({ children }: { children: ReactNode }) {
  const holder = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const [context, setContext] = useState<LeafletContextInterface | null>(null);
  useEffect(() => {
    const node = holder.current;
    if (!node) return;
    let map = mapRef.current;
    if (map) {
      map.invalidateSize();
    } else {
      map = new LeafletMap(node, { minZoom: 2, maxZoom: 10, scrollWheelZoom: false, attributionControl: true });
      map.setView(MADAGASCAR, 5);
      mapRef.current = map;
      setContext(createLeafletContext(map));
    }
    const live = map;
    return () => {
      // Passive cleanups run after React has detached a deleted node: still connected = only hidden.
      if (node.isConnected) return;
      live.remove();
      mapRef.current = null;
    };
  }, []);
  return (
    <div ref={holder} className="h-full w-full">
      {context && <LeafletContext value={context}>{children}</LeafletContext>}
    </div>
  );
}

/**
 * One circle per region, its area following what circulated there in the last 7 days, darker as
 * the share of high-risk dossiers grows. The selected region is filled and ringed in ink. Loaded
 * with `next/dynamic` and `ssr: false`: Leaflet needs the window.
 */
export default function VeilleMap({ regions, selected, onSelect, country = "Madagascar" }: { regions: RegionCount[]; selected: string | null; onSelect: (region: string | null) => void; country?: string }) {
  const placed = regions.filter((r) => r.lat != null && r.lng != null && r.last_7d > 0);
  return (
    <LiveMap>
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
    </LiveMap>
  );
}
