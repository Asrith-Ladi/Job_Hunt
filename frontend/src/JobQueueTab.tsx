import { useMemo, useState } from "react";
import { api } from "./api";
import type { AppConfig, GmailRunHistoryEntry, JobRow, SavedApplication, Scalar } from "./types";
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

type QueueView = "all" | "saved" | "possible" | "needs_official" | "official_ready" | "applied";

function readableDate(value: string): string {
  if (!value) return "Date unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
}

function readableDateTime(value: string): string {
  if (!value) return "Time unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
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
  if (view === "saved") return group.items.some((item) => item.persisted);
  if (view === "possible") return group.possibleDuplicate;
  if (view === "needs_official") return group.items.some((item) => !rowOfficialUrl(item.row));
  if (view === "official_ready") return group.items.some((item) => Boolean(rowOfficialUrl(item.row)));
  if (view === "applied") return group.items.some((item) => isApplied(item.row));
  return true;
}

function groupMatchesSearch(group: QueueGroup, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return true;
  return group.items.some((item) => (
    [
      item.row.company,
      item.row.title,
      item.row.location,
      item.row.provider,
      item.row.referral_name,
      item.row.experience_text,
      item.row.years_of_experience,
    ].some((value) => scalarText(value).toLocaleLowerCase().includes(needle))
    || item.referralCandidates.some((candidate) =>
      [candidate.name, candidate.position].some((value) =>
        value.toLocaleLowerCase().includes(needle),
      ),
    )
  ));
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
  if (run.transient) {
    return (
      <article className="run-output-row">
        <span className={`source-chip ${sourceClass(source)}`}>{SOURCE_LABELS[source]}</span>
        <div><strong>{run.rows.length} temporary result{run.rows.length === 1 ? "" : "s"}</strong><small>{readableDate(run.run_started_at)} · not written to Drive</small></div>
        <span className="temporary-result-badge">Session only</span>
      </article>
    );
  }
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

function GmailRunHistoryMenu({
  history,
  loadedRunId,
  loadingRunId,
  onLoad,
}: {
  history: GmailRunHistoryEntry[];
  loadedRunId: string;
  loadingRunId: string;
  onLoad: (runId: string) => void;
}) {
  return (
    <details className="run-outputs-menu run-history-menu">
      <summary>Previous Gmail runs · {history.length}</summary>
      <div>
        <header className="run-history-heading">
          <strong>Previously generated Gmail job files</strong>
          <span>Load one for review without rereading Gmail.</span>
        </header>
        {history.length ? history.map((entry) => {
          const loaded = entry.run_id === loadedRunId;
          return (
            <article className={`run-history-row ${loaded ? "loaded" : ""}`} key={entry.run_id}>
              <div className="run-history-main">
                <strong>{entry.file_name}{entry.is_current ? " · Current" : ""}</strong>
                <small>{readableDateTime(entry.run_started_at)}</small>
                <span>
                  {entry.rows_exported} saved job{entry.rows_exported === 1 ? "" : "s"}
                  {" · "}{entry.unchanged_jobs} unchanged{" · "}{entry.messages_read} emails read
                </span>
              </div>
              <div className="run-history-actions">
                <button
                  type="button"
                  disabled={loaded || !entry.loadable || Boolean(loadingRunId)}
                  onClick={() => onLoad(entry.run_id)}
                >
                  {loadingRunId === entry.run_id ? "Loading…" : loaded ? "Loaded" : "Load jobs"}
                </button>
                {entry.loadable && <a href={`/api/gmail/runs/${encodeURIComponent(entry.run_id)}/download`}>Excel</a>}
                {entry.drive_url && <a href={entry.drive_url} target="_blank" rel="noreferrer">Drive ↗</a>}
              </div>
            </article>
          );
        }) : <p className="run-history-empty">No saved Gmail runs are available yet.</p>}
      </div>
    </details>
  );
}

function SourceRecord({
  item,
  applicationStatuses,
  historical,
  saving,
  onUpdate,
  onPersist,
  onOpenJob,
  onCopied,
}: {
  item: QueueItem;
  applicationStatuses: string[];
  historical: boolean;
  saving: boolean;
  onUpdate: (item: QueueItem, column: string, value: Scalar) => void;
  onPersist: (item: QueueItem, column: string, value: Scalar) => void;
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
  const referralCandidates = item.referralCandidates.length
    ? item.referralCandidates
    : referralName
      ? [{
          name: referralName,
          position: scalarText(row.referral_position),
          profile_url: referralProfile,
          message: referralMessage,
        }]
      : [];
  const runChange = changeStatus(row.run_change_status);
  return (
    <article className="queue-source-record">
      <div className="record-source-rail">
        <span className={`source-chip ${sourceClass(item.source)}`}>{SOURCE_LABELS[item.source]}</span>
        <small>{scalarText(row.provider) || scalarText(row.alert_source) || "Source record"}</small>
        {runChange && <em className={`change-badge ${runChange.className}`}>{runChange.label}</em>}
        {historical && <em className="change-badge historical">Previous run</em>}
        <em className={`change-badge ${item.persisted ? "persisted" : "temporary"}`}>
          {item.persisted ? "Saved in Drive" : "Temporary result"}
        </em>
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

        {referralCandidates.length > 0 && (
          <div className="record-referral-list">
            <div className="record-referral-summary">
              <small>Offline referral leads</small>
              <span>{referralCandidates.length} ranked same-company profile{referralCandidates.length === 1 ? "" : "s"} · verify before messaging</span>
            </div>
            <div className="record-referral-candidates">
              {referralCandidates.map((candidate, index) => (
                <div className="record-referral-row" key={`${candidate.profile_url}:${candidate.name}:${index}`}>
                  <div>
                    <small>{index === 0 ? "Best-ranked match" : `Alternative ${index + 1}`}</small>
                    {candidate.profile_url
                      ? <a href={candidate.profile_url} target="_blank" rel="noreferrer">{candidate.name} ↗</a>
                      : <strong>{candidate.name}</strong>}
                    <span>{candidate.position || "Role unavailable in saved export"}</span>
                  </div>
                  {candidate.message && (
                    <button className="text-action" type="button" onClick={() => onCopied(candidate.message)}>
                      Copy referral request
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="record-review-grid">
          <label className="field">
            <span>Application status</span>
            <select
              value={scalarText(row.application_status) || "not_started"}
              disabled={saving}
              onChange={(event) => onPersist(item, "application_status", event.target.value)}
            >
              {applicationStatuses.map((statusValue) => <option key={statusValue}>{statusValue}</option>)}
            </select>
          </label>
          <label className="field record-notes-field">
            <span>Review notes</span>
            <textarea
              rows={2}
              value={scalarText(row.notes)}
              placeholder="Decision, follow-up, or verification note…"
              onChange={(event) => onUpdate(item, "notes", event.target.value)}
              onBlur={(event) => {
                const value = event.currentTarget.value.trim();
                if (value || item.persisted) onPersist(item, "notes", value);
              }}
            />
          </label>
          {!item.persisted && (
            <button
              className="secondary-button record-save-action"
              type="button"
              disabled={saving}
              onClick={() => onPersist(item, "application_status", "saved")}
            >
              {saving ? "Saving…" : "Save for later"}
            </button>
          )}
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
  savedApplications,
  gmailHistory,
  loadingHistoryRunId,
  onUpdate,
  onPersist,
  savingJobIds,
  onOpenJob,
  onGoToSetup,
  onLoadGmailRun,
  onNotice,
}: {
  config: AppConfig;
  runs: WorkspaceRuns;
  savedApplications: SavedApplication[];
  gmailHistory: GmailRunHistoryEntry[];
  loadingHistoryRunId: string;
  onUpdate: (item: QueueItem, column: string, value: Scalar) => void;
  onPersist: (item: QueueItem, column: string, value: Scalar) => void;
  savingJobIds: Set<string>;
  onOpenJob: (item: QueueItem) => void;
  onGoToSetup: () => void;
  onLoadGmailRun: (runId: string) => void;
  onNotice: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<"all" | WorkspaceSource>("all");
  const [view, setView] = useState<QueueView>("all");
  const items = useMemo(
    () => flattenRuns(runs, savedApplications),
    [runs, savedApplications],
  );
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
  const savedCount = items.filter((item) => item.persisted).length;
  const currentResultCount = items.filter((item) => item.currentResult).length;
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
    const hasSavedGmailRuns = gmailHistory.length > 0;
    return (
      <main className="product-page queue-page">
        <section className="premium-empty-state">
          <span className="empty-state-mark">01</span>
          <p className="eyebrow">Application queue</p>
          <h2>{hasSavedGmailRuns ? "No current or saved jobs are visible." : "Search at least one source to build your review queue."}</h2>
          <p>{hasSavedGmailRuns
            ? "Start a fresh search or open a previous Gmail workbook to review jobs collected before the canonical application queue was introduced."
            : "Temporary Gmail alerts, official company results, and structured ATS jobs stay as separate evidence records until you explicitly save one."}</p>
          <div className="empty-state-actions">
            {hasSavedGmailRuns && (
              <GmailRunHistoryMenu
                history={gmailHistory}
                loadedRunId={runs.gmail?.run_id ?? ""}
                loadingRunId={loadingHistoryRunId}
                onLoad={onLoadGmailRun}
              />
            )}
            <button className="primary-button" type="button" onClick={onGoToSetup}>Open Search</button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="product-page queue-page">
      <section className="page-intro queue-intro">
        <div>
          <p className="eyebrow">Temporary results · permanent application tracking</p>
          <h2>Review the opportunity once. Keep every source as evidence.</h2>
          <p>Searches stay in this session. Save for later, status changes, and notes create or update the permanent Drive queue.</p>
        </div>
        <div className="queue-heading-actions">
          {gmailHistory.length > 0 && (
            <GmailRunHistoryMenu
              history={gmailHistory}
              loadedRunId={runs.gmail?.run_id ?? ""}
              loadingRunId={loadingHistoryRunId}
              onLoad={onLoadGmailRun}
            />
          )}
          <details className="run-outputs-menu">
            <summary>{runEntries.length} visible source set{runEntries.length === 1 ? "" : "s"}</summary>
            <div>{runEntries.map(([runSource, run]) => <RunOutput source={runSource} run={run} key={runSource} />)}</div>
          </details>
          <span className="queue-persistence-state">
            {savingJobIds.size ? `Saving ${savingJobIds.size} job${savingJobIds.size === 1 ? "" : "s"}…` : `${savedCount} saved permanently`}
          </span>
        </div>
      </section>

      {runs.gmail?.historical && (
        <section className="historical-run-banner" role="status">
          <div>
            <strong>Previous Gmail run loaded</strong>
            <span>{runs.gmail.file_name} remains unchanged. Any new tracking action saves to the canonical application queue.</span>
          </div>
          <span className="safe-badge">Editable tracking</span>
        </section>
      )}

      <section className="queue-stats" aria-label="Queue summary">
        <button className={view === "all" ? "active" : ""} type="button" onClick={() => setView("all")}><small>Visible jobs</small><strong>{items.length}</strong><span>{currentResultCount} current search results</span></button>
        <button className={view === "saved" ? "active" : ""} type="button" onClick={() => setView("saved")}><small>Saved jobs</small><strong>{savedCount}</strong><span>Permanent Drive queue</span></button>
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
            <button className={view === "saved" ? "active" : ""} onClick={() => setView("saved")} type="button">Saved</button>
            <button className={view === "possible" ? "active" : ""} onClick={() => setView("possible")} type="button">Possible duplicates ({possibleCount})</button>
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
                      historical={Boolean(runs[item.source]?.historical)}
                      saving={savingJobIds.has(item.id)}
                      onUpdate={onUpdate}
                      onPersist={onPersist}
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
