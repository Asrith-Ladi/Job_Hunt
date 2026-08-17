import type { DiscoveryRunArtifact, JobRow, RunArtifact, Scalar } from "./types";

export type WorkspaceSource = "gmail" | "company_portals" | "ats_sources";
export type WorkspaceRun = RunArtifact | DiscoveryRunArtifact;
export type WorkspaceRuns = Record<WorkspaceSource, WorkspaceRun | null>;

export interface QueueItem {
  id: string;
  source: WorkspaceSource;
  runId: string;
  row: JobRow;
}

export interface QueueGroup {
  id: string;
  items: QueueItem[];
  primary: QueueItem;
  possibleDuplicate: boolean;
  sourceLabels: string[];
}

export const SOURCE_LABELS: Record<WorkspaceSource, string> = {
  gmail: "Gmail",
  company_portals: "Company portal",
  ats_sources: "ATS",
};

export function scalarText(value: Scalar | undefined): string {
  return value === null || value === undefined ? "" : String(value).trim();
}

function normalized(value: Scalar | undefined): string {
  return scalarText(value)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function stableHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function rowRecordId(source: WorkspaceSource, row: JobRow, index: number): string {
  const supplied = scalarText(row.job_record_id) || scalarText(row.external_job_id);
  return `${source}:${supplied || index}`;
}

export function flattenRuns(runs: WorkspaceRuns): QueueItem[] {
  return (Object.entries(runs) as Array<[WorkspaceSource, WorkspaceRun | null]>).flatMap(
    ([source, run]) =>
      (run?.rows ?? []).map((row, index) => ({
        id: rowRecordId(source, row, index),
        source,
        runId: run?.run_id ?? "",
        row,
      })),
  );
}

function possibleMatchKey(item: QueueItem): string {
  const company = normalized(item.row.company);
  const title = normalized(item.row.title);
  const location = normalized(item.row.location);
  const requisition = normalized(item.row.requisition_id ?? item.row.external_job_id);

  if (company && requisition) return `requisition|${company}|${requisition}`;
  if (company && title) return `facts|${company}|${title}|${location}`;

  const officialUrl = scalarText(item.row.official_url)
    .replace(/[?#].*$/, "")
    .replace(/\/$/, "")
    .toLocaleLowerCase();
  if (officialUrl) return `official|${officialUrl}`;
  return `single|${item.id}`;
}

function itemEvidenceScore(item: QueueItem): number {
  let score = item.source === "gmail" ? 0 : 10;
  if (scalarText(item.row.official_url)) score += 20;
  if (scalarText(item.row.description)) score += 8;
  if (scalarText(item.row.posted_at ?? item.row.alert_posted_at)) score += 4;
  if (scalarText(item.row.requisition_id ?? item.row.external_job_id)) score += 3;
  return score;
}

function itemTimestamp(item: QueueItem): number {
  const raw = scalarText(
    item.row.posted_at
      ?? item.row.alert_posted_at
      ?? item.row.email_received_at
      ?? item.row.discovered_at
      ?? item.row.first_seen_at,
  );
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function groupQueueItems(items: QueueItem[]): QueueGroup[] {
  const buckets = new Map<string, QueueItem[]>();
  items.forEach((item) => {
    const key = possibleMatchKey(item);
    buckets.set(key, [...(buckets.get(key) ?? []), item]);
  });

  return Array.from(buckets.entries())
    .map(([key, bucket]) => {
      const ordered = [...bucket].sort((left, right) => {
        const evidence = itemEvidenceScore(right) - itemEvidenceScore(left);
        return evidence || itemTimestamp(right) - itemTimestamp(left);
      });
      const sources = Array.from(new Set(bucket.map((item) => SOURCE_LABELS[item.source])));
      return {
        id: `group-${stableHash(key)}`,
        items: ordered,
        primary: ordered[0],
        possibleDuplicate: ordered.length > 1,
        sourceLabels: sources,
      };
    })
    .sort((left, right) => itemTimestamp(right.primary) - itemTimestamp(left.primary));
}

export function rowExperience(row: JobRow): string {
  return scalarText(row.years_of_experience ?? row.experience_text) || "Not stated";
}

export function rowDate(row: JobRow): string {
  return scalarText(
    row.posted_at
      ?? row.alert_posted_at
      ?? row.email_received_at
      ?? row.discovered_at
      ?? row.first_seen_at,
  );
}

export function rowAlertUrl(item: QueueItem): string {
  return item.source === "gmail" ? scalarText(item.row.source_url) : "";
}

export function rowOfficialUrl(row: JobRow): string {
  return scalarText(row.official_url);
}
