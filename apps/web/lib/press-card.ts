import type { components } from "@checky/shared";
import { api } from "@/lib/api";

type CardUpload = components["schemas"]["CardUploadOut"];
export type Profile = components["schemas"]["JournalistProfileOut"];

export const CARD_MAX_BYTES = 8 * 1024 * 1024;
export const CARD_ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";
const CARD_TYPES = new Set(CARD_ACCEPT.split(","));

/** The error code the form shows, or null when the file can be sent. Checked before the account exists. */
export function cardProblem(file: File | null): "card_required" | "card_type" | "card_size" | null {
  if (!file) return "card_required";
  if (!CARD_TYPES.has(file.type)) return "card_type";
  if (file.size > CARD_MAX_BYTES) return "card_size";
  return null;
}

export type ProfileInput = { phone: string; outlet: string; card_number?: string; file: File };

/**
 * Presigned upload of the press card straight to storage, then the API reads the file back and
 * refuses anything that is not a real, readable image or PDF before saving the profile.
 */
export async function saveProfile(input: ProfileInput): Promise<Profile> {
  const { file } = input;
  const up = await api<CardUpload>("/me/press-card/upload-url", {
    method: "POST",
    body: JSON.stringify({ filename: file.name, mime: file.type, size_bytes: file.size }),
  });
  const put = await fetch(up.upload_url, { method: "PUT", headers: up.headers, body: file });
  if (!put.ok) throw new Error(`upload ${put.status}`);
  return api<Profile>("/me/profile", {
    method: "PUT",
    body: JSON.stringify({
      phone: input.phone,
      outlet: input.outlet,
      card_number: input.card_number || null,
      card_key: up.card_key,
      card_filename: file.name,
    }),
  });
}
