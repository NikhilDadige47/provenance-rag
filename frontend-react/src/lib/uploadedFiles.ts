const blobsByName = new Map<string, string>();
const blobsByDocId = new Map<string, string>();
const namesByDocId = new Map<string, string>();

export function rememberUploadedFile(file: File): string {
  const previous = blobsByName.get(file.name);
  if (previous) URL.revokeObjectURL(previous);
  const url = URL.createObjectURL(file);
  blobsByName.set(file.name, url);
  return url;
}

export function bindUploadedDoc(docId: string, fileName: string): void {
  if (!docId || !fileName) return;
  namesByDocId.set(docId, fileName);
  const blob = blobsByName.get(fileName);
  if (blob) blobsByDocId.set(docId, blob);
}

export function originalNameForDoc(docId: string, fallback: string): string {
  return namesByDocId.get(docId) || fallback;
}

export function previewUrlForDoc(docId: string, fileName: string): string | undefined {
  return blobsByDocId.get(docId) || blobsByName.get(fileName);
}

export function clearUploadedFiles(): void {
  for (const url of blobsByName.values()) {
    URL.revokeObjectURL(url);
  }
  blobsByName.clear();
  blobsByDocId.clear();
  namesByDocId.clear();
}
