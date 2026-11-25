/** The visitor's address as the closest proxy saw it: the LAST entry of x-forwarded-for. Earlier entries are written by the visitor and mean nothing. */
export function lastHop(header: string | null): string {
  if (!header) return "";
  const parts = header.split(",").map((p) => p.trim()).filter(Boolean);
  return parts.length ? parts[parts.length - 1]! : "";
}
