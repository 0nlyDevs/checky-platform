import type { components } from "@fanilo/shared";
import { api } from "@/lib/api";

type UploadOut = components["schemas"]["UploadOut"];
export type Source = components["schemas"]["SourceOut"];

/**
 * Presigned upload straight to storage (the file never passes through the API), then
 * `complete` turns it into a source and starts its analysis. XHR rather than fetch, for progress.
 */
export async function uploadFile(
  ws: string,
  file: File,
  itemId: string | undefined,
  onProgress: (fraction: number) => void,
): Promise<Source> {
  const up = await api<UploadOut>(`/workspaces/${ws}/files/upload-url`, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, mime: file.type || "application/octet-stream", size_bytes: file.size }),
  });
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", up.upload_url);
    for (const [k, v] of Object.entries(up.headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`upload ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("upload network"));
    xhr.send(file);
  });
  return api<Source>(`/workspaces/${ws}/files/${up.file_id}/complete`, {
    method: "POST",
    body: JSON.stringify(itemId ? { item_id: itemId } : {}),
  });
}
