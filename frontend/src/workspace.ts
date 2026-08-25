import type {
  DiscoveryRunArtifact,
  JobRow,
  ReferralCandidate,
  RunArtifact,
  SavedApplication,
  Scalar,
} from "./types";

export type WorkspaceSource = "gmail" | "company_portals" | "ats_sources";
export type WorkspaceRun = RunArtifact | DiscoveryRunArtifact;
export type WorkspaceRuns = Record<WorkspaceSource, WorkspaceRun | null>;

export interface QueueItem {
  id: string;
  source: WorkspaceSource;
  runId: string;
  row: JobRow;
  referralCandidates: ReferralCandidate[];
  persisted: boolean;
  currentResult: boolean;
  applicationId: string;
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

function persistenceKeys(source: WorkspaceSource, row: JobRow): string[] {
  const recordId = scalarText(row.job_record_id ?? row.external_job_id);
  if (recordId) return [`${source}|record|${recordId}`];
  const officialUrl = scalarText(row.official_url).replace(/[?#].*$/, "").replace(/\/$/, "").toLocaleLowerCase();
  if (officialUrl) return [`${source}|official|${officialUrl}`];
  const sourceUrl = scalarText(row.source_url).replace(/[?#].*$/, "").replace(/\/$/, "").toLocaleLowerCase();
  if (sourceUrl) return [`${source}|source|${sourceUrl}`];
  const facts = [row.company, row.title, row.location].map(normalized).join("|");
  return facts.replaceAll("|", "") ? [`${source}|facts|${facts}`] : [];
}

function mergedRow(current: JobRow, saved: JobRow): JobRow {
  const output: JobRow = { ...saved, ...current };
  for (const key of ["official_url", "apply_url", "notes", "application_status"] as const) {
    if (scalarText(saved[key])) output[key] = saved[key];
  }
  return output;
}

export function flattenRuns(
  runs: WorkspaceRuns,
  applications: SavedApplication[] = [],
): QueueItem[] {
  const savedByKey = new Map<string, SavedApplication>();
  applications.forEach((application) => {
    persistenceKeys(application.source, application.row).forEach((key) => {
      if (!savedByKey.has(key)) savedByKey.set(key, application);
    });
  });
  const usedApplications = new Set<string>();
  const currentItems = (Object.entries(runs) as Array<[WorkspaceSource, WorkspaceRun | null]>).flatMap(
    ([source, run]) =>
      (run?.rows ?? []).map((sourceRow, index) => {
        const saved = persistenceKeys(source, sourceRow)
          .map((key) => savedByKey.get(key))
          .find(Boolean);
        if (saved) usedApplications.add(saved.application_id);
        const row = saved ? mergedRow(sourceRow, saved.row) : sourceRow;
        const recordId = scalarText(row.job_record_id ?? row.external_job_id);
        return {
          id: rowRecordId(source, row, index),
          source,
          runId: run?.run_id ?? "",
          row,
          referralCandidates: recordId
            ? run?.referral_candidates?.[recordId] ?? saved?.referral_candidates ?? []
            : saved?.referral_candidates ?? [],
          persisted: Boolean(saved),
          currentResult: Boolean(run?.transient),
          applicationId: saved?.application_id ?? "",
        };
      }),
  );
  const savedOnly = applications
    .filter((application) => !usedApplications.has(application.application_id))
    .map((application, index) => ({
      id: `saved:${application.application_id}`,
      source: application.source,
      runId: "application_queue",
      row: application.row,
      referralCandidates: application.referral_candidates ?? [],
      persisted: true,
      currentResult: false,
      applicationId: application.application_id,
    } satisfies QueueItem));
  return [...currentItems, ...savedOnly];
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
