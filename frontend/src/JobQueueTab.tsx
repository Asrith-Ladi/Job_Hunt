import { useMemo, useState } from "react";
import { api } from "./api";
import type { AppConfig, JobRow, Scalar } from "./types";
import {
  SOURCE_LABELS,
  flattenRuns,
  groupQueueItems,
  rowAlertUrl,
  rowDate,
  rowExperience,
  rowOfficialUrl,
  scalarText,
  type QueueGroup,
  type QueueItem,
  type WorkspaceRuns,
  type WorkspaceSource,
} from "./workspace";

type QueueView = "all" | "possible" | "needs_official" | "official_ready" | "applied";

function readableDate(value: string): string {
  if (!value) return "Date unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
}

function officialStatus(row: JobRow): { label: string; tone: string } {
  const sourceStatus = scalarText(row.source_status ?? row.active_status).toLocaleLowerCase();
  if (["expired", "closed", "inactive"].includes(sourceStatus)) return { label: "Closed", tone: "danger" };
  if (rowOfficialUrl(row)) return { label: sourceStatus === "active" ? "Active official job" : "Official link found", tone: "success" };
  return { label: "Official match needed", tone: "warning" };
}

function isApplied(row: JobRow): boolean {
  return ["applied", "interviewing", "shortlisted", "offer"].includes(
    scalarText(row.application_status).toLocaleLowerCase(),
  );
}

function groupMatchesView(group: QueueGroup, view: QueueView): boolean {
  if (view === "possible") return group.possibleDuplicate;
  if (view === "needs_official") return group.items.some((item) => !rowOfficialUrl(item.row));
  if (view === "official_ready") return group.items.some((item) => Boolean(rowOfficialUrl(item.row)));
  if (view === "applied") return group.items.some((item) => isApplied(item.row));
  return true;
}

function groupMatchesSearch(group: QueueGroup, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return true;
  return group.items.some((item) => [
    item.row.company,
    item.row.title,
    item.row.location,
    item.row.provider,
    item.row.referral_name,
    item.row.experience_text,
    item.row.years_of_experience,
  ].some((value) => scalarText(value).toLocaleLowerCase().includes(needle)));
}

function sourceClass(source: WorkspaceSource): string {
  return source.replace("_sources", "").replace("_portals", "");
}

function changeStatus(value: Scalar | undefined): { label: string; className: string } | null {
  const normalized = scalarText(value).toLocaleLowerCase();
  if (normalized === "new") return { label: "New this run", className: "new" };
  if (normalized === "changed") return { label: "Changed", className: "changed" };
  if (normalized === "previously_seen") return { label: "Previously seen", className: "seen" };
  if (normalized === "new_or_changed") return { label: "New / changed", className: "changed" };
  return null;
}

function RunOutput({ source, run }: { source: WorkspaceSource; run: NonNullable<WorkspaceRuns[WorkspaceSource]> }) {
  const downloadUrl = source === "gmail"
    ? `/api/gmail/runs/${encodeURIComponent(run.run_id)}/download`
    : api.discoveryDownloadUrl(source, run.run_id);
  return (
    <article className="run-output-row">
      <span className={`source-chip ${sourceClass(source)}`}>{SOURCE_LABELS[source]}</span>
      <div><strong>{run.file_name}</strong><small>{readableDate(run.run_started_at)}</small></div>
      <div className="run-output-actions">
        <a href={downloadUrl}>Excel</a>
        {run.drive_url && <a href={run.drive_url} target="_blank" rel="noreferrer">Drive ↗</a>}
      </div>
    </article>
  );
}

function SourceRecord({
  item,
  applicationStatuses,
  onUpdate,
  onOpenJob,
  onCopied,
}: {
  item: QueueItem;
  applicationStatuses: string[];
  onUpdate: (item: QueueItem, column: string, value: Scalar) => void;
  onOpenJob: (item: QueueItem) => void;
  onCopied: (message: string) => void;
}) {
  const row = item.row;
  const alertUrl = rowAlertUrl(item);
  const officialUrl = rowOfficialUrl(row);
  const status = officialStatus(row);
  const referralName = scalarText(row.referral_name);
  const referralProfile = scalarText(row.referral_profile_url);
  const referralMessage = scalarText(row.referral_message);
  const runChange = changeStatus(row.run_change_status);
  return (
    <article className="queue-source-record">
      <div className="record-source-rail">
        <span className={`source-chip ${sourceClass(item.source)}`}>{SOURCE_LABELS[item.source]}</span>
        <small>{scalarText(row.provider) || scalarText(row.alert_source) || "Source record"}</small>
        {runChange && <em className={`change-badge ${runChange.className}`}>{runChange.label}</em>}
      </div>
      <div className="record-main">
        <div className="record-heading">
          <div>
            <h4>{scalarText(row.title) || "Untitled job"}</h4>
            <p>{scalarText(row.company) || "Company unavailable"}{scalarText(row.location) ? ` · ${scalarText(row.location)}` : ""}</p>
          </div>
          <span className={`status-badge ${status.tone}`}>{status.label}</span>
        </div>

        <div className="record-evidence-grid">
          <div><small>Experience</small><strong>{rowExperience(row)}</strong></div>
          <div><small>Published / received</small><strong>{readableDate(rowDate(row))}</strong></div>
          <div><small>Experience fit</small><strong>{scalarText(row.experience_fit) || "Not assessed"}</strong></div>
          <div><small>Identity</small><strong>{scalarText(row.source_confidence ?? row.parse_confidence) || "Source evidence retained"}</strong></div>
        </div>

        <div className="record-link-grid">
          {item.source === "gmail" && (
            <div>
              <small>Alert job URL</small>
              {alertUrl ? <a href={alertUrl} target="_blank" rel="noreferrer">Open LinkedIn/Naukri alert ↗</a> : <span>Not available</span>}
            </div>
          )}
          <div>
            <small>Official job URL</small>
            {officialUrl ? <a href={officialUrl} target="_blank" rel="noreferrer">Open employer posting ↗</a> : <span>Not verified yet</span>}
          </div>
        </div>

        {referralName && (
          <div className="record-referral-row">
            <div>
              <small>Offline referral lead</small>
              {referralProfile ? <a href={referralProfile} target="_blank" rel="noreferrer">{referralName} ↗</a> : <strong>{referralName}</strong>}
              <span>{scalarText(row.referral_position)}</span>
            </div>
            {referralMessage && <button className="text-action" type="button" onClick={() => onCopied(referralMessage)}>Copy referral request</button>}
          </div>
        )}

        <div className="record-review-grid">
          <label className="field">
            <span>Application status</span>
            <select value={scalarText(row.application_status)} onChange={(event) => onUpdate(item, "application_status", event.target.value)}>
              {applicationStatuses.map((statusValue) => <option key={statusValue}>{statusValue}</option>)}
            </select>
          </label>
          <label className="field record-notes-field">
            <span>Review notes</span>
            <textarea rows={2} value={scalarText(row.notes)} placeholder="Decision, follow-up, or verification note…" onChange={(event) => onUpdate(item, "notes", event.target.value)} />
          </label>
          <button className="primary-button record-primary-action" type="button" onClick={() => onOpenJob(item)}>
            {officialUrl ? "Review JD + documents" : "Find official JD"}
          </button>
        </div>
      </div>
    </article>
  );
}

export default function JobQueueTab({
  config,
  runs,
  dirtySources,
  saving,
  onSave,
  onUpdate,
  onOpenJob,
  onGoToSetup,
  onNotice,
}: {
  config: AppConfig;
  runs: WorkspaceRuns;
  dirtySources: Set<WorkspaceSource>;
  saving: boolean;
  onSave: () => void;
  onUpdate: (item: QueueItem, column: string, value: Scalar) => void;
  onOpenJob: (item: QueueItem) => void;
  onGoToSetup: () => void;
  onNotice: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<"all" | WorkspaceSource>("all");
  const [view, setView] = useState<QueueView>("all");
  const items = useMemo(() => flattenRuns(runs), [runs]);
  const groups = useMemo(() => groupQueueItems(items), [items]);
  const filtered = useMemo(
    () => groups.filter((group) =>
      groupMatchesView(group, view)
      && groupMatchesSearch(group, query)
      && (source === "all" || group.items.some((item) => item.source === source)),
    ),
    [groups, query, source, view],
  );
  const possibleCount = groups.filter((group) => group.possibleDuplicate).length;
  const officialCount = items.filter((item) => rowOfficialUrl(item.row)).length;
  const appliedCount = items.filter((item) => isApplied(item.row)).length;
  const previouslySeenCount = items.filter(
    (item) => scalarText(item.row.run_change_status).toLocaleLowerCase() === "previously_seen",
  ).length;
  const newOrChangedCount = items.length - previouslySeenCount;
  const runEntries = (Object.entries(runs) as Array<[WorkspaceSource, WorkspaceRuns[WorkspaceSource]]>)
    .filter((entry): entry is [WorkspaceSource, NonNullable<WorkspaceRuns[WorkspaceSource]>] => Boolean(entry[1]));

  const copyReferral = async (message: string) => {
    try {
      await navigator.clipboard.writeText(message);
      onNotice("Referral request copied. Review it before sending.");
    } catch {
      onNotice("Clipboard access was unavailable. Select and copy the message from the job tool instead.");
    }
  };

  if (!items.length) {
    return (
      <main className="product-page queue-page">
        <section className="premium-empty-state">
          <span className="empty-state-mark">01</span>
          <p className="eyebrow">Application queue</p>
          <h2>Run at least one source to build your review queue.</h2>
          <p>Your Gmail alerts, official company results, and structured ATS jobs will stay as separate evidence records while likely matches are grouped for verification.</p>
          <button className="primary-button" type="button" onClick={onGoToSetup}>Open Run Setup</button>
        </section>
      </main>
    );
  }

  return (
    <main className="product-page queue-page">
      <section className="page-intro queue-intro">
        <div>
          <p className="eyebrow">Verification-first application queue</p>
          <h2>Review the opportunity once. Keep every source as evidence.</h2>
          <p>Possible duplicates are grouped visually and remain unmerged until you verify the official posting.</p>
        </div>
        <div className="queue-heading-actions">
          <details className="run-outputs-menu">
            <summary>{runEntries.length} current run output{runEntries.length === 1 ? "" : "s"}</summary>
            <div>{runEntries.map(([runSource, run]) => <RunOutput source={runSource} run={run} key={runSource} />)}</div>
          </details>
          <button className="primary-button" type="button" disabled={!dirtySources.size || saving} onClick={onSave}>
            {saving ? "Saving to Drive…" : dirtySources.size ? `Save ${dirtySources.size} changed source${dirtySources.size === 1 ? "" : "s"}` : "Saved"}
          </button>
        </div>
      </section>

      <section className="queue-stats" aria-label="Queue summary">
        <button className={view === "all" ? "active" : ""} type="button" onClick={() => setView("all")}><small>Current matches</small><strong>{items.length}</strong><span>{newOrChangedCount} new/changed · {previouslySeenCount} seen</span></button>
        <button className={view === "possible" ? "active" : ""} type="button" onClick={() => setView("possible")}><small>Possible same jobs</small><strong>{possibleCount}</strong><span>Needs verification</span></button>
        <button className={view === "official_ready" ? "active" : ""} type="button" onClick={() => setView("official_ready")}><small>Official links</small><strong>{officialCount}</strong><span>JD actions ready</span></button>
        <button className={view === "applied" ? "active" : ""} type="button" onClick={() => setView("applied")}><small>In progress</small><strong>{appliedCount}</strong><span>Applied or later</span></button>
      </section>

      <section className="queue-workspace-card">
        <div className="queue-toolbar">
          <label className="search-field queue-search">
            <span aria-hidden="true">⌕</span>
            <input value={query} placeholder="Search company, title, location, provider, or referral…" onChange={(event) => setQuery(event.target.value)} />
          </label>
          <div className="segmented-filter" aria-label="Queue state">
            <button className={view === "all" ? "active" : ""} onClick={() => setView("all")} type="button">All</button>
            <button className={view === "needs_official" ? "active" : ""} onClick={() => setView("needs_official")} type="button">Needs official match</button>
            <button className={view === "official_ready" ? "active" : ""} onClick={() => setView("official_ready")} type="button">Official ready</button>
          </div>
          <select value={source} onChange={(event) => setSource(event.target.value as "all" | WorkspaceSource)} aria-label="Filter queue by source">
            <option value="all">All sources</option>
            <option value="gmail">Gmail</option>
            <option value="company_portals">Company portals</option>
            <option value="ats_sources">ATS</option>
          </select>
          <span className="queue-result-count">{filtered.length} job unit{filtered.length === 1 ? "" : "s"}</span>
        </div>

        <div className="queue-column-guide" aria-hidden="true">
          <span>Job</span><span>Location</span><span>Experience</span><span>Sources</span><span>Official status</span><span>Application</span>
        </div>

        <div className="job-group-list">
          {filtered.map((group) => {
            const primary = group.primary.row;
            const status = officialStatus(primary);
            const application = scalarText(primary.application_status) || "not_started";
            return (
              <details className={`job-unit ${group.possibleDuplicate ? "possible-group" : ""}`} key={group.id}>
                <summary className="job-unit-summary">
                  <span className="job-summary-title"><strong>{scalarText(primary.title) || "Untitled job"}</strong><small>{scalarText(primary.company) || "Company unavailable"}</small></span>
                  <span>{scalarText(primary.location) || "Not stated"}</span>
                  <span>{rowExperience(primary)}</span>
                  <span className="source-stack">{group.sourceLabels.map((labelValue) => <em key={labelValue}>{labelValue}</em>)}</span>
                  <span className={`status-badge ${status.tone}`}>{status.label}</span>
                  <span className={`value-chip ${application}`}>{application.replaceAll("_", " ")}</span>
                  <span className="expand-indicator">⌄</span>
                </summary>
                <div className="job-unit-body">
                  {group.possibleDuplicate && (
                    <div className="possible-match-note">
                      <div><strong>Possible same job · not merged</strong><span>{group.items.length} source records share a requisition or normalized company/title/location signature. Open the links and verify before treating them as one official job.</span></div>
                      <span className="safe-badge">Evidence preserved</span>
                    </div>
                  )}
                  {group.items.map((item) => (
                    <SourceRecord
                      item={item}
                      applicationStatuses={config.application_statuses}
                      onUpdate={onUpdate}
                      onOpenJob={onOpenJob}
                      onCopied={copyReferral}
                      key={item.id}
                    />
                  ))}
                </div>
              </details>
            );
          })}
          {!filtered.length && <div className="queue-no-results"><strong>No job units match this view.</strong><span>Adjust the source, status, or text filter without changing the saved records.</span></div>}
        </div>
      </section>
    </main>
  );
}
