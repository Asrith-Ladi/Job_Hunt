import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import DiscoveryTab from "./DiscoveryTab";
import JobIntelligencePanel from "./JobIntelligencePanel";
import NetworkReviewsTab from "./NetworkReviewsTab";
import type { AppConfig, GoogleStatus, JobRow, RunArtifact, RunSettings, Scalar } from "./types";

type Tab = "gmail" | "company_portals" | "ats_sources" | "network_reviews";

const DEFAULT_VISIBLE_COLUMNS = [
  "alert_source",
  "company",
  "title",
  "location",
  "years_of_experience",
  "experience_fit",
  "source_url",
  "official_url",
  "referral_count",
  "referral_name",
  "referral_position",
  "referral_eligibility",
  "referral_message",
  "application_status",
  "notes",
];

const COLUMN_LABELS: Record<string, string> = {
  alert_source: "Source",
  company: "Company",
  title: "Job title",
  location: "Location",
  years_of_experience: "Experience",
  experience_fit: "5–8 year fit",
  source_url: "Alert job",
  official_url: "Official job",
  application_status: "Application status",
  notes: "Notes",
  email_received_at: "Email received",
  alert_posted_at: "Alert posted",
  parse_status: "Parse status",
  parse_confidence: "Parse confidence",
  company_match: "Company match",
  experience_min_years: "Minimum years",
  experience_max_years: "Maximum years",
  experience_source: "Experience source",
  email_subject: "Email subject",
  first_seen_at: "First seen",
  last_seen_at: "Last seen",
  job_record_id: "Job record ID",
  gmail_message_id: "Gmail message ID",
  evidence_message_ids: "Evidence message IDs",
  owner_id: "Owner",
  referral_count: "Referral candidates",
  referral_name: "Suggested referral",
  referral_position: "Connection role",
  referral_profile_url: "LinkedIn profile",
  referral_match_status: "Referral match",
  referral_eligibility: "Why my profile may fit",
  referral_message: "LinkedIn referral request",
};

const EMPTY_SETTINGS: RunSettings = {
  sources: ["linkedin", "naukri"],
  labels_by_source: {
    linkedin: "Job_Alerts/LinkedIn",
    naukri: "Job_Alerts/Naukari",
  },
  gmail_query: "",
  company_allowlist: "",
  include_unmatched_companies: true,
  lookback_days: 30,
  max_messages: 500,
  target_experience_min_years: 5,
  target_experience_max_years: 8,
  strict_experience_filter: false,
  override_query: false,
};

function valueText(value: Scalar | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function labelFor(column: string): string {
  return COLUMN_LABELS[column] ?? column.replaceAll("_", " ");
}

function metric(summary: Record<string, Scalar>, key: string): number {
  const value = Number(summary[key] ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function generatedQuery(settings: RunSettings): string {
  const labels = settings.sources
    .map((source) => settings.labels_by_source[source]?.trim())
    .filter(Boolean)
    .map((label) => `label:${label}`);
  const labelQuery = labels.length > 1 ? `{${labels.join(" ")}}` : labels[0] ?? "";
  return labelQuery ? `${labelQuery} newer_than:${settings.lookback_days}d` : "";
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    if (!document.execCommand("copy")) throw new Error("Copy is unavailable in this browser.");
  } finally {
    document.body.removeChild(textarea);
  }
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("gmail");
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [settings, setSettings] = useState<RunSettings>(EMPTY_SETTINGS);
  const [run, setRun] = useState<RunArtifact | null>(null);
  const [rows, setRows] = useState<JobRow[]>([]);
  const [visibleColumns, setVisibleColumns] = useState<string[]>(DEFAULT_VISIBLE_COLUMNS);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [intelligenceJob, setIntelligenceJob] = useState<JobRow | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error" | "info"; text: string } | null>(null);

  useEffect(() => {
    const callbackState = new URLSearchParams(window.location.search).get("google");
    if (callbackState) {
      const message =
        callbackState === "connected"
          ? { kind: "success" as const, text: "Google connected successfully." }
          : callbackState === "denied"
            ? { kind: "info" as const, text: "Google authorization was cancelled. No mailbox data was read." }
            : { kind: "error" as const, text: "Google authorization could not be completed. Please reconnect." };
      setNotice(message);
      window.history.replaceState({}, "", window.location.pathname);
    }

    Promise.all([api.config(), api.googleStatus(), api.latestRun()])
      .then(([appConfig, googleStatus, latest]) => {
        setConfig(appConfig);
        setGoogle(googleStatus);
        setSettings((current) => ({
          ...current,
          labels_by_source: appConfig.labels_by_source,
          lookback_days: appConfig.lookback_days,
          max_messages: appConfig.max_messages,
          target_experience_min_years: appConfig.target_experience_min_years,
          target_experience_max_years: appConfig.target_experience_max_years,
          include_unmatched_companies: appConfig.include_unmatched_companies,
          strict_experience_filter: appConfig.strict_experience_filter,
        }));
        if (latest.run) {
          setRun(latest.run);
          setRows(latest.run.rows);
        }
      })
      .catch((error: Error) => setNotice({ kind: "error", text: error.message }))
      .finally(() => setLoading(false));
  }, []);

  const filteredRows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return rows.filter((row) => {
      if (sourceFilter !== "all" && valueText(row.alert_source) !== sourceFilter) return false;
      if (statusFilter !== "all" && valueText(row.application_status) !== statusFilter) return false;
      if (!needle) return true;
      return [
        row.company,
        row.title,
        row.location,
        row.years_of_experience,
        row.referral_name,
        row.referral_position,
      ]
        .map(valueText)
        .some((value) => value.toLocaleLowerCase().includes(needle));
    });
  }, [rows, search, sourceFilter, statusFilter]);

  const connectGoogle = async () => {
    try {
      setNotice(null);
      const response = await api.startGoogle();
      window.location.assign(response.authorization_url);
    } catch (error) {
      setNotice({ kind: "error", text: (error as Error).message });
    }
  };

  const runGmail = async () => {
    if (!settings.sources.length) {
      setNotice({ kind: "error", text: "Select at least one Gmail alert source." });
      return;
    }
    if (dirty && !window.confirm("This will replace the unsaved on-screen edits with a new Gmail run. Continue?")) {
      return;
    }
    setRunning(true);
    setNotice({ kind: "info", text: "Reading approved Gmail labels and preparing the Drive workbook…" });
    try {
      const response = await api.runGmail(settings);
      setRun(response.run);
      setRows(response.run.rows);
      setDirty(false);
      setNotice({
        kind: "success",
        text: `Gmail run completed. ${response.run.rows.length} new or changed jobs are ready to review.`,
      });
    } catch (error) {
      setNotice({ kind: "error", text: (error as Error).message });
    } finally {
      setRunning(false);
    }
  };

  const saveRows = async () => {
    if (!run) return;
    setSaving(true);
    setNotice({ kind: "info", text: "Updating the same Excel workbook locally and in Drive…" });
    try {
      const response = await api.saveRows(run.run_id, rows);
      setRun(response.run);
      setRows(response.run.rows);
      setDirty(false);
      setNotice({ kind: "success", text: "Your edits were saved to the same Excel and Drive file." });
    } catch (error) {
      setNotice({ kind: "error", text: (error as Error).message });
    } finally {
      setSaving(false);
    }
  };

  const updateCell = (recordId: string, column: string, value: Scalar) => {
    setRows((current) =>
      current.map((row) =>
        valueText(row.job_record_id) === recordId ? { ...row, [column]: value } : row,
      ),
    );
    setDirty(true);
  };

  const toggleSource = (source: string) => {
    setSettings((current) => ({
      ...current,
      sources: current.sources.includes(source)
        ? current.sources.filter((item) => item !== source)
        : [...current.sources, source],
    }));
  };

  const toggleColumn = (column: string) => {
    setVisibleColumns((current) =>
      current.includes(column)
        ? current.filter((item) => item !== column)
        : [...current, column],
    );
  };

  const copyReferralMessage = async (message: string) => {
    try {
      await copyText(message);
      setNotice({ kind: "success", text: "LinkedIn referral request copied." });
    } catch (error) {
      setNotice({ kind: "error", text: (error as Error).message });
    }
  };

  if (loading) {
    return (
      <main className="loading-screen">
        <div className="brand-mark">JH</div>
        <p>Preparing your job workspace…</p>
      </main>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">JH</div>
          <div>
            <p className="eyebrow">Personal workspace</p>
            <h1>Job Hunt</h1>
          </div>
        </div>
        <div className={`connection-pill ${google?.connected ? "connected" : "disconnected"}`}>
          <span className="status-dot" />
          <span>{google?.connected ? "Google connected" : "Google disconnected"}</span>
          {!google?.connected && (
            <button className="link-button" type="button" onClick={connectGoogle}>
              {google?.reconnect_required ? "Reconnect" : "Connect"}
            </button>
          )}
        </div>
      </header>

      <nav className="source-tabs" aria-label="Job sources">
        <button className={activeTab === "gmail" ? "active" : ""} onClick={() => setActiveTab("gmail")}>
          <span>01</span> Gmail alerts <b>Ready</b>
        </button>
        <button
          className={activeTab === "company_portals" ? "active" : ""}
          onClick={() => setActiveTab("company_portals")}
        >
          <span>02</span> Company portals <b>Ready</b>
        </button>
        <button className={activeTab === "ats_sources" ? "active" : ""} onClick={() => setActiveTab("ats_sources")}>
          <span>03</span> ATS sources <b>Ready</b>
        </button>
        <button
          className={activeTab === "network_reviews" ? "active" : ""}
          onClick={() => setActiveTab("network_reviews")}
        >
          <span>04</span> Network reviews <b>Ready</b>
        </button>
      </nav>

      {notice && (
        <div className={`notice ${notice.kind}`} role="status" aria-live="polite">
          <span>{notice.kind === "success" ? "✓" : notice.kind === "error" ? "!" : "i"}</span>
          <p>{notice.text}</p>
          <button type="button" aria-label="Dismiss message" onClick={() => setNotice(null)}>×</button>
        </div>
      )}

      {activeTab === "gmail" ? (
        <main className="workspace">
          <aside className="settings-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Manual run</p>
                <h2>Gmail settings</h2>
              </div>
              <span className="safe-badge">Read only</span>
            </div>

            <fieldset>
              <legend>Alert sources</legend>
              <div className="source-options">
                {(["linkedin", "naukri"] as const).map((source) => (
                  <label className="check-card" key={source}>
                    <input
                      type="checkbox"
                      checked={settings.sources.includes(source)}
                      onChange={() => toggleSource(source)}
                    />
                    <span className={`source-icon ${source}`}>{source === "linkedin" ? "in" : "n"}</span>
                    <span>{source === "linkedin" ? "LinkedIn" : "Naukri"}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            {(["linkedin", "naukri"] as const).map((source) => (
              <label className="field" key={source}>
                <span>{source === "linkedin" ? "LinkedIn" : "Naukri"} Gmail label</span>
                <input
                  value={settings.labels_by_source[source] ?? ""}
                  onChange={(event) =>
                    setSettings((current) => ({
                      ...current,
                      labels_by_source: { ...current.labels_by_source, [source]: event.target.value },
                    }))
                  }
                />
              </label>
            ))}

            <div className="field-row">
              <label className="field">
                <span>Lookback days</span>
                <input
                  type="number"
                  min="1"
                  max="90"
                  value={settings.lookback_days}
                  onChange={(event) => setSettings({ ...settings, lookback_days: Number(event.target.value) })}
                />
              </label>
              <label className="field">
                <span>Max emails</span>
                <input
                  type="number"
                  min="1"
                  max="5000"
                  value={settings.max_messages}
                  onChange={(event) => setSettings({ ...settings, max_messages: Number(event.target.value) })}
                />
              </label>
            </div>

            <label className="field">
              <span>Companies <small>optional, one per line</small></span>
              <textarea
                rows={3}
                value={settings.company_allowlist}
                placeholder="Wipro\nAccenture\nGoogle"
                onChange={(event) => setSettings({ ...settings, company_allowlist: event.target.value })}
              />
            </label>

            <div className="field-row">
              <label className="field">
                <span>Minimum years</span>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={settings.target_experience_min_years}
                  onChange={(event) =>
                    setSettings({ ...settings, target_experience_min_years: Number(event.target.value) })
                  }
                />
              </label>
              <label className="field">
                <span>Maximum years</span>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={settings.target_experience_max_years}
                  onChange={(event) =>
                    setSettings({ ...settings, target_experience_max_years: Number(event.target.value) })
                  }
                />
              </label>
            </div>

            <label className="toggle-row">
              <input
                type="checkbox"
                checked={settings.include_unmatched_companies}
                onChange={(event) => setSettings({ ...settings, include_unmatched_companies: event.target.checked })}
              />
              <span>Keep unmatched or unknown companies</span>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={settings.strict_experience_filter}
                onChange={(event) => setSettings({ ...settings, strict_experience_filter: event.target.checked })}
              />
              <span>Exclude roles known outside 5–8 years</span>
            </label>

            <details className="advanced">
              <summary>Advanced Gmail query</summary>
              <label className="toggle-row compact">
                <input
                  type="checkbox"
                  checked={settings.override_query}
                  onChange={(event) => setSettings({ ...settings, override_query: event.target.checked })}
                />
                <span>Override generated query</span>
              </label>
              <textarea
                rows={3}
                disabled={!settings.override_query}
                value={settings.override_query ? settings.gmail_query : generatedQuery(settings)}
                onChange={(event) => setSettings({ ...settings, gmail_query: event.target.value })}
              />
            </details>

            <button
              className="primary-button run-button"
              type="button"
              onClick={runGmail}
              disabled={!google?.connected || running || saving}
            >
              {running ? <span className="spinner" /> : <span>▶</span>}
              {running ? "Running Gmail workflow…" : "Run Gmail alerts"}
            </button>
            <p className="privacy-note">
              No LLM, portal search, mailbox modification, or application submission runs here.
            </p>
          </aside>

          <section className="results-panel">
            <div className="results-heading">
              <div>
                <p className="eyebrow">Current workbook</p>
                <h2>{run ? run.file_name : "No Gmail run yet"}</h2>
                <p>
                  {run
                    ? `Run ${run.run_id} · ${new Date(run.run_started_at).toLocaleString()}`
                    : "Connect Google, review the settings, and run your approved alert labels."}
                </p>
              </div>
              <div className="heading-actions">
                {run?.drive_url && (
                  <a className="secondary-button" href={run.drive_url} target="_blank" rel="noreferrer">Open in Drive ↗</a>
                )}
                {run && (
                  <a className="secondary-button" href={`/api/gmail/runs/${encodeURIComponent(run.run_id)}/download`}>
                    Download Excel
                  </a>
                )}
                <button
                  className="primary-button"
                  type="button"
                  onClick={saveRows}
                  disabled={!run || !dirty || saving || running}
                >
                  {saving ? "Saving…" : dirty ? "Save Excel + Drive" : "Saved"}
                </button>
              </div>
            </div>

            {run ? (
              <>
                <div className="metrics-grid">
                  <MetricCard label="Emails read" value={metric(run.summary, "messages_read")} />
                  <MetricCard label="Jobs parsed" value={metric(run.summary, "jobs_parsed")} />
                  <MetricCard
                    label="Duplicates merged"
                    value={Math.max(0, metric(run.summary, "jobs_parsed") - metric(run.summary, "jobs_after_deduplication"))}
                  />
                  <MetricCard label="Previously seen" value={metric(run.summary, "jobs_unchanged_from_prior_runs")} />
                  <MetricCard label="Referral leads" value={metric(run.summary, "jobs_with_referral_candidate")} />
                  <MetricCard label="Rows to review" value={rows.length} accent />
                </div>

                <div className="table-toolbar">
                  <label className="search-field">
                    <span>⌕</span>
                    <input
                      value={search}
                      placeholder="Search company, title, location, experience…"
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </label>
                  <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} aria-label="Filter by source">
                    <option value="all">All sources</option>
                    <option value="linkedin">LinkedIn</option>
                    <option value="naukri">Naukri</option>
                  </select>
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filter by application status">
                    <option value="all">All statuses</option>
                    {run.application_statuses.map((status) => <option key={status}>{status}</option>)}
                  </select>
                  <details className="column-picker">
                    <summary>Columns · {visibleColumns.length}</summary>
                    <div>
                      {run.job_columns.map((column) => (
                        <label key={column}>
                          <input
                            type="checkbox"
                            checked={visibleColumns.includes(column)}
                            onChange={() => toggleColumn(column)}
                          />
                          <span>{labelFor(column)}</span>
                        </label>
                      ))}
                    </div>
                  </details>
                  <span className="row-count">{filteredRows.length} of {rows.length} rows</span>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th className="job-tools-heading">Job tools</th>
                        {visibleColumns.map((column) => <th key={column}>{labelFor(column)}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRows.map((row) => {
                        const recordId = valueText(row.job_record_id);
                        return (
                          <tr key={recordId}>
                            <td className="job-tools-cell">
                              <button
                                className="table-action-button"
                                type="button"
                                onClick={() => setIntelligenceJob(row)}
                              >
                                Official JD + resume
                              </button>
                            </td>
                            {visibleColumns.map((column) => (
                              <JobCell
                                key={column}
                                row={row}
                                column={column}
                                editable={run.editable_columns.includes(column)}
                                applicationStatuses={run.application_statuses}
                                experienceStatuses={run.experience_fit_statuses}
                                onChange={(value) => updateCell(recordId, column, value)}
                                onCopy={copyReferralMessage}
                              />
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {!filteredRows.length && <div className="empty-table">No rows match the current filters.</div>}
                </div>
                <p className="table-help">
                  Referral candidates come from your offline LinkedIn export snapshot. Verify their current employer before messaging; use Copy message for a concise, editable request.
                </p>
              </>
            ) : (
              <div className="empty-state">
                <div>✦</div>
                <h3>Your normalized alert jobs will appear here</h3>
                <p>
                  The backend reads only the labels and rolling date range you approve, removes duplicates, then creates one timestamped Excel file in Drive.
                </p>
                {!google?.connected && (
                  <button className="primary-button" type="button" onClick={connectGoogle}>Connect Google</button>
                )}
              </div>
            )}
          </section>
        </main>
      ) : activeTab === "company_portals" ? (
        <DiscoveryTab
          mode="company_portals"
          googleConnected={Boolean(google?.connected)}
          maxSources={config?.discovery_max_sources_per_run ?? 10}
          onConnectGoogle={connectGoogle}
          onNotice={setNotice}
        />
      ) : activeTab === "ats_sources" ? (
        <DiscoveryTab
          mode="ats_sources"
          googleConnected={Boolean(google?.connected)}
          maxSources={config?.discovery_max_sources_per_run ?? 10}
          onConnectGoogle={connectGoogle}
          onNotice={setNotice}
        />
      ) : (
        <NetworkReviewsTab onNotice={setNotice} />
      )}
      {intelligenceJob && (
        <JobIntelligencePanel
          job={intelligenceJob}
          googleConnected={Boolean(google?.connected)}
          onClose={() => setIntelligenceJob(null)}
          onOfficialUrl={(url) => {
            const recordId = valueText(intelligenceJob.job_record_id);
            updateCell(recordId, "official_url", url);
            setIntelligenceJob((current) => current ? { ...current, official_url: url } : current);
          }}
        />
      )}
    </div>
  );
}

function MetricCard({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return (
    <article className={`metric-card ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
    </article>
  );
}

function JobCell({
  row,
  column,
  editable,
  applicationStatuses,
  experienceStatuses,
  onChange,
  onCopy,
}: {
  row: JobRow;
  column: string;
  editable: boolean;
  applicationStatuses: string[];
  experienceStatuses: string[];
  onChange: (value: Scalar) => void;
  onCopy: (value: string) => void;
}) {
  const value = valueText(row[column]);
  const isUrl = ["source_url", "official_url", "referral_profile_url"].includes(column);

  if (editable && column === "application_status") {
    return (
      <td><select value={value} onChange={(event) => onChange(event.target.value)}>{applicationStatuses.map((item) => <option key={item}>{item}</option>)}</select></td>
    );
  }
  if (editable && column === "experience_fit") {
    return (
      <td><select value={value} onChange={(event) => onChange(event.target.value)}>{experienceStatuses.map((item) => <option key={item}>{item}</option>)}</select></td>
    );
  }
  if (editable && column === "notes") {
    return <td className="wide-cell"><textarea rows={3} value={value} onChange={(event) => onChange(event.target.value)} placeholder="Add a review note…" /></td>;
  }
  if (editable) {
    const numberField = column === "experience_min_years" || column === "experience_max_years";
    return (
      <td className={column === "title" ? "wide-cell" : ""}>
        <div className={isUrl ? "url-editor" : ""}>
          <input
            type={numberField ? "number" : "text"}
            step={numberField ? "0.5" : undefined}
            value={value}
            onChange={(event) => onChange(numberField && event.target.value ? Number(event.target.value) : event.target.value)}
          />
          {isUrl && value && <a href={value} target="_blank" rel="noreferrer" aria-label={`Open ${labelFor(column)}`}>↗</a>}
        </div>
      </td>
    );
  }
  if (isUrl) {
    const linkText = column === "source_url"
      ? "Open alert job"
      : column === "official_url"
        ? "Open official job"
        : "Open LinkedIn profile";
    return (
      <td>
        {value ? <a className="job-link" href={value} target="_blank" rel="noreferrer">{linkText} ↗</a> : <span className="muted">Not available</span>}
      </td>
    );
  }
  if (column === "referral_name") {
    const profileUrl = valueText(row.referral_profile_url);
    return (
      <td className="referral-name-cell">
        {value && profileUrl ? (
          <a className="job-link" href={profileUrl} target="_blank" rel="noreferrer">{value} ↗</a>
        ) : value ? value : <span className="muted">No offline match</span>}
      </td>
    );
  }
  if (column === "referral_message") {
    return (
      <td className="referral-message-cell">
        {value ? (
          <div className="referral-message">
            <LinkifiedText value={value} />
            <button type="button" onClick={() => onCopy(value)}>Copy message</button>
          </div>
        ) : <span className="muted">No message available</span>}
      </td>
    );
  }
  if (column === "referral_eligibility") {
    return <td className="eligibility-cell">{value || <span className="muted">Not assessed</span>}</td>;
  }
  if (column === "alert_source") {
    return <td><span className={`source-chip ${value}`}>{value || "unknown"}</span></td>;
  }
  if (column === "experience_fit" || column === "parse_status" || column === "application_status") {
    return <td><span className={`value-chip ${value}`}>{value || "unknown"}</span></td>;
  }
  return <td className={column === "title" || column === "email_subject" ? "wide-cell" : ""}>{value || <span className="muted">—</span>}</td>;
}

function LinkifiedText({ value }: { value: string }) {
  const parts = value.split(/(https?:\/\/[^\s]+)/g);
  return (
    <p>
      {parts.map((part, index) =>
        part.startsWith("http://") || part.startsWith("https://") ? (
          <a key={`${part}-${index}`} href={part} target="_blank" rel="noreferrer">{part}</a>
        ) : <span key={`${part}-${index}`}>{part}</span>,
      )}
    </p>
  );
}

export default App;
