import { useEffect, useMemo, useState } from "react";
import { api, type DiscoveryMode } from "./api";
import JobIntelligencePanel from "./JobIntelligencePanel";
import type {
  CompanyRegistryEntry,
  DiscoveryFiltersSettings,
  DiscoveryRunArtifact,
  JobRow,
  ManualAtsSource,
  Scalar,
  SourceCheckRow,
} from "./types";

type Notice = { kind: "success" | "error" | "info"; text: string };

const DEFAULT_FILTERS: DiscoveryFiltersSettings = {
  keyword: "",
  location: "",
  posted_within_days: 15,
  include_unknown_dates: true,
  max_jobs_per_source: 100,
  target_experience_min_years: 5,
  target_experience_max_years: 8,
  strict_experience_filter: false,
};

const DEFAULT_COLUMNS = [
  "company",
  "title",
  "location",
  "experience_text",
  "experience_fit",
  "posted_at",
  "provider",
  "official_url",
  "description",
  "application_status",
  "notes",
];

const LABELS: Record<string, string> = {
  job_record_id: "Job record ID",
  company: "Company",
  title: "Job title",
  location: "Location",
  provider: "Provider",
  source_identifier: "Source identifier",
  source_type: "Source type",
  external_job_id: "External job ID",
  official_url: "Official job",
  apply_url: "Apply link",
  source_url: "Source endpoint",
  description: "Job description",
  department: "Department",
  employment_type: "Employment type",
  workplace_type: "Workplace type",
  experience_text: "Experience",
  experience_min_years: "Minimum years",
  experience_max_years: "Maximum years",
  experience_fit: "5–8 year fit",
  posted_at: "Published",
  updated_at: "Updated",
  date_provenance: "Date provenance",
  discovered_at: "Discovered",
  first_seen_at: "First seen",
  last_seen_at: "Last seen",
  source_confidence: "Confidence",
  source_status: "Source status",
  application_status: "Application status",
  notes: "Notes",
};

const EMPTY_MANUAL: ManualAtsSource = {
  company: "",
  provider: "greenhouse",
  identifier: "",
  region: "global",
  careers_url: "",
};

function text(value: Scalar | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function numberMetric(summary: Record<string, Scalar>, key: string): number {
  const value = Number(summary[key] ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function label(column: string): string {
  return LABELS[column] ?? column.replaceAll("_", " ");
}

export default function DiscoveryTab({
  mode,
  googleConnected,
  maxSources,
  onConnectGoogle,
  onNotice,
}: {
  mode: DiscoveryMode;
  googleConnected: boolean;
  maxSources: number;
  onConnectGoogle: () => void;
  onNotice: (notice: Notice | null) => void;
}) {
  const companyMode = mode === "company_portals";
  const [registry, setRegistry] = useState<CompanyRegistryEntry[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [manualSources, setManualSources] = useState<ManualAtsSource[]>([]);
  const [manualDraft, setManualDraft] = useState<ManualAtsSource>(EMPTY_MANUAL);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [registrySearch, setRegistrySearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [includeDetectionOnly, setIncludeDetectionOnly] = useState(false);
  const [run, setRun] = useState<DiscoveryRunArtifact | null>(null);
  const [rows, setRows] = useState<JobRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [visibleColumns, setVisibleColumns] = useState(DEFAULT_COLUMNS);
  const [intelligenceJob, setIntelligenceJob] = useState<JobRow | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([api.registry(), api.latestDiscoveryRun(mode)])
      .then(([registryResult, latest]) => {
        if (!active) return;
        setRegistry(registryResult.companies);
        if (latest.run) {
          setRun(latest.run);
          setRows(latest.run.rows);
        }
      })
      .catch((error: Error) => {
        if (active) onNotice({ kind: "error", text: error.message });
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [mode, onNotice]);

  const categories = useMemo(
    () => Array.from(new Set(registry.map((item) => item.category))).sort(),
    [registry],
  );
  const providers = useMemo(
    () =>
      Array.from(new Set(registry.map((item) => item.detection.provider || "unknown"))).sort(),
    [registry],
  );
  const registryRows = useMemo(() => {
    const needle = registrySearch.trim().toLocaleLowerCase();
    return registry.filter((item) => {
      if (!companyMode && !includeDetectionOnly && !item.adapter_ready) return false;
      if (categoryFilter !== "all" && item.category !== categoryFilter) return false;
      if (providerFilter !== "all" && item.detection.provider !== providerFilter) return false;
      if (!needle) return true;
      return [item.company, item.sector, item.source_type_label, item.detection.provider]
        .some((value) => value.toLocaleLowerCase().includes(needle));
    });
  }, [registry, registrySearch, categoryFilter, providerFilter, companyMode, includeDetectionOnly]);

  const resultProviders = useMemo(
    () => Array.from(new Set(rows.map((row) => text(row.provider)).filter(Boolean))).sort(),
    [rows],
  );
  const filteredRows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return rows.filter((row) => {
      if (sourceFilter !== "all" && text(row.provider) !== sourceFilter) return false;
      if (statusFilter !== "all" && text(row.application_status) !== statusFilter) return false;
      if (!needle) return true;
      return [row.company, row.title, row.location, row.description, row.experience_text]
        .map(text)
        .some((value) => value.toLocaleLowerCase().includes(needle));
    });
  }, [rows, search, sourceFilter, statusFilter]);

  const selectionCount = selected.length + manualSources.length;

  const toggleCompany = (companyId: string) => {
    setSelected((current) => {
      if (current.includes(companyId)) return current.filter((item) => item !== companyId);
      if (current.length + manualSources.length >= maxSources) {
        onNotice({ kind: "info", text: `A manual run is limited to ${maxSources} sources.` });
        return current;
      }
      return [...current, companyId];
    });
  };

  const addManualSource = () => {
    if (!manualDraft.company.trim() || !manualDraft.identifier.trim()) {
      onNotice({ kind: "error", text: "Enter both the company and public ATS identifier." });
      return;
    }
    if (selectionCount >= maxSources) {
      onNotice({ kind: "info", text: `A manual run is limited to ${maxSources} sources.` });
      return;
    }
    setManualSources((current) => [...current, { ...manualDraft }]);
    setManualDraft(EMPTY_MANUAL);
  };

  const runDiscovery = async () => {
    if (!selectionCount) {
      onNotice({ kind: "error", text: "Select at least one company or add one ATS identifier." });
      return;
    }
    if (dirty && !window.confirm("Replace the unsaved on-screen edits with a new run?")) return;
    setRunning(true);
    onNotice({
      kind: "info",
      text: `Checking ${selectionCount} approved public source${selectionCount === 1 ? "" : "s"} and preparing the dated workbook…`,
    });
    try {
      const response = await api.runDiscovery(mode, selected, manualSources, filters);
      setRun(response.run);
      setRows(response.run.rows);
      setDirty(false);
      onNotice({
        kind: "success",
        text: `${companyMode ? "Company portal" : "ATS"} run completed. ${response.run.rows.length} new or changed jobs are ready to review.`,
      });
    } catch (error) {
      onNotice({ kind: "error", text: (error as Error).message });
    } finally {
      setRunning(false);
    }
  };

  const saveRows = async () => {
    if (!run) return;
    setSaving(true);
    onNotice({ kind: "info", text: "Updating the same local and Drive workbook…" });
    try {
      const response = await api.saveDiscoveryRows(mode, run.run_id, rows);
      setRun(response.run);
      setRows(response.run.rows);
      setDirty(false);
      onNotice({ kind: "success", text: "Edits saved to the same Excel and Drive file." });
    } catch (error) {
      onNotice({ kind: "error", text: (error as Error).message });
    } finally {
      setSaving(false);
    }
  };

  const updateCell = (recordId: string, column: string, value: Scalar) => {
    setRows((current) =>
      current.map((row) =>
        text(row.job_record_id) === recordId ? { ...row, [column]: value } : row,
      ),
    );
    setDirty(true);
  };

  const toggleColumn = (column: string) => {
    setVisibleColumns((current) =>
      current.includes(column)
        ? current.filter((item) => item !== column)
        : [...current, column],
    );
  };

  if (loading) {
    return <main className="discovery-loading">Loading the company source registry…</main>;
  }

  return (
    <>
    <main className="workspace discovery-workspace">
      <aside className="settings-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Manual run · maximum {maxSources}</p>
            <h2>{companyMode ? "Company portals" : "ATS sources"}</h2>
          </div>
          <span className="safe-badge">Public only</span>
        </div>

        <label className="field">
          <span>Find a registry company</span>
          <input
            value={registrySearch}
            placeholder="Company, sector, or provider"
            onChange={(event) => setRegistrySearch(event.target.value)}
          />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Category</span>
            <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              <option value="all">All categories</option>
              {categories.map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Provider</span>
            <select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}>
              <option value="all">All providers</option>
              {providers.map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
        </div>
        {!companyMode && (
          <label className="toggle-row compact">
            <input
              type="checkbox"
              checked={includeDetectionOnly}
              onChange={(event) => setIncludeDetectionOnly(event.target.checked)}
            />
            <span>Include detection-only platforms for an auditable manual fallback</span>
          </label>
        )}

        <div className="registry-list" aria-label="Company source registry">
          {registryRows.map((item) => (
            <label className={`registry-item ${selected.includes(item.company_id) ? "selected" : ""}`} key={item.company_id}>
              <input
                type="checkbox"
                checked={selected.includes(item.company_id)}
                onChange={() => toggleCompany(item.company_id)}
              />
              <span>
                <strong>{item.company}</strong>
                <small>{item.category} · {item.detection.provider || "generic"}</small>
              </span>
              <em className={item.adapter_ready ? "ready" : "fallback"}>
                {item.adapter_ready ? "API" : "fallback"}
              </em>
            </label>
          ))}
          {!registryRows.length && <p className="registry-empty">No registry companies match these filters.</p>}
        </div>
        <p className="selection-count">{selectionCount} of {maxSources} sources selected</p>

        {!companyMode && (
          <details className="manual-source">
            <summary>Add a public ATS identifier</summary>
            <label className="field">
              <span>Company</span>
              <input value={manualDraft.company} onChange={(event) => setManualDraft({ ...manualDraft, company: event.target.value })} />
            </label>
            <div className="field-row">
              <label className="field">
                <span>Provider</span>
                <select
                  value={manualDraft.provider}
                  onChange={(event) => setManualDraft({ ...manualDraft, provider: event.target.value as ManualAtsSource["provider"] })}
                >
                  <option value="greenhouse">Greenhouse</option>
                  <option value="lever">Lever</option>
                  <option value="workable">Workable</option>
                  <option value="smartrecruiters">SmartRecruiters</option>
                </select>
              </label>
              <label className="field">
                <span>Region</span>
                <select
                  value={manualDraft.region}
                  onChange={(event) => setManualDraft({ ...manualDraft, region: event.target.value as ManualAtsSource["region"] })}
                >
                  <option value="global">Global</option>
                  <option value="eu">EU (Lever only)</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span>Board token, slug, subdomain, or company identifier</span>
              <input value={manualDraft.identifier} onChange={(event) => setManualDraft({ ...manualDraft, identifier: event.target.value })} />
            </label>
            <button type="button" className="secondary-button manual-add" onClick={addManualSource}>Add source</button>
            {manualSources.map((source, index) => (
              <div className="manual-chip" key={`${source.provider}-${source.identifier}-${index}`}>
                <span>{source.company} · {source.provider}/{source.identifier}</span>
                <button type="button" onClick={() => setManualSources((current) => current.filter((_, itemIndex) => itemIndex !== index))}>×</button>
              </div>
            ))}
          </details>
        )}

        <details className="advanced" open>
          <summary>Deterministic job filters</summary>
          <label className="field">
            <span>Keyword <small>optional, comma-separated alternatives</small></span>
            <input value={filters.keyword} placeholder="machine learning, data scientist" onChange={(event) => setFilters({ ...filters, keyword: event.target.value })} />
          </label>
          <label className="field">
            <span>Location <small>optional</small></span>
            <input value={filters.location} placeholder="Hyderabad, Bengaluru, remote" onChange={(event) => setFilters({ ...filters, location: event.target.value })} />
          </label>
          <div className="field-row">
            <label className="field">
              <span>Posted within days</span>
              <input type="number" min="1" max="90" value={filters.posted_within_days} onChange={(event) => setFilters({ ...filters, posted_within_days: Number(event.target.value) })} />
            </label>
            <label className="field">
              <span>Max jobs/source</span>
              <input type="number" min="1" max="250" value={filters.max_jobs_per_source} onChange={(event) => setFilters({ ...filters, max_jobs_per_source: Number(event.target.value) })} />
            </label>
          </div>
          <div className="field-row">
            <label className="field">
              <span>Minimum years</span>
              <input type="number" min="0" step="0.5" value={filters.target_experience_min_years} onChange={(event) => setFilters({ ...filters, target_experience_min_years: Number(event.target.value) })} />
            </label>
            <label className="field">
              <span>Maximum years</span>
              <input type="number" min="0" step="0.5" value={filters.target_experience_max_years} onChange={(event) => setFilters({ ...filters, target_experience_max_years: Number(event.target.value) })} />
            </label>
          </div>
          <label className="toggle-row compact">
            <input type="checkbox" checked={filters.include_unknown_dates} onChange={(event) => setFilters({ ...filters, include_unknown_dates: event.target.checked })} />
            <span>Keep jobs whose official source gives no publication date</span>
          </label>
          <label className="toggle-row compact">
            <input type="checkbox" checked={filters.strict_experience_filter} onChange={(event) => setFilters({ ...filters, strict_experience_filter: event.target.checked })} />
            <span>Exclude roles known outside the target experience range</span>
          </label>
        </details>

        {googleConnected ? (
          <button className="primary-button run-button" type="button" onClick={runDiscovery} disabled={running || saving || !selectionCount}>
            {running && <span className="spinner" />}
            {running ? "Checking public sources…" : `Run ${companyMode ? "company portals" : "ATS sources"}`}
          </button>
        ) : (
          <button className="primary-button run-button" type="button" onClick={onConnectGoogle}>Connect Google to save in Drive</button>
        )}
        <p className="privacy-note">No LLM, employer login, JavaScript execution, CAPTCHA bypass, or application submission runs here.</p>
      </aside>

      <section className="results-panel">
        <div className="results-heading">
          <div>
            <p className="eyebrow">Current {companyMode ? "company portal" : "ATS"} workbook</p>
            <h2>{run ? run.file_name : "No run yet"}</h2>
            <p>{run ? `Run ${run.run_id} · ${new Date(run.run_started_at).toLocaleString()}` : "Select a small source batch, set optional filters, and run it manually."}</p>
          </div>
          <div className="heading-actions">
            {run?.drive_url && <a className="secondary-button" href={run.drive_url} target="_blank" rel="noreferrer">Open in Drive ↗</a>}
            {run && <a className="secondary-button" href={api.discoveryDownloadUrl(mode, run.run_id)}>Download Excel</a>}
            <button className="primary-button" type="button" onClick={saveRows} disabled={!run || !dirty || saving || running}>
              {saving ? "Saving…" : dirty ? "Save Excel + Drive" : "Saved"}
            </button>
          </div>
        </div>

        {run ? (
          <>
            <div className="metrics-grid">
              <Metric label="Sources checked" value={numberMetric(run.summary, "sources_checked")} />
              <Metric label="Jobs found" value={numberMetric(run.summary, "jobs_found")} />
              <Metric label="Duplicates merged" value={Math.max(0, numberMetric(run.summary, "jobs_found") - numberMetric(run.summary, "jobs_after_deduplication"))} />
              <Metric label="Previously seen" value={numberMetric(run.summary, "jobs_unchanged_from_prior_runs")} />
              <Metric label="Rows to review" value={rows.length} accent />
            </div>

            <div className="table-toolbar">
              <label className="search-field">
                <span>⌕</span>
                <input value={search} placeholder="Search company, title, location, description…" onChange={(event) => setSearch(event.target.value)} />
              </label>
              <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} aria-label="Filter by provider">
                <option value="all">All providers</option>
                {resultProviders.map((value) => <option key={value}>{value}</option>)}
              </select>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filter by application status">
                <option value="all">All statuses</option>
                {run.application_statuses.map((value) => <option key={value}>{value}</option>)}
              </select>
              <details className="column-picker">
                <summary>Columns · {visibleColumns.length}</summary>
                <div>
                  {run.job_columns.map((column) => (
                    <label key={column}>
                      <input type="checkbox" checked={visibleColumns.includes(column)} onChange={() => toggleColumn(column)} />
                      <span>{label(column)}</span>
                    </label>
                  ))}
                </div>
              </details>
              <span className="row-count">{filteredRows.length} of {rows.length} rows</span>
            </div>

            <div className="table-wrap">
              <table>
                <thead><tr><th className="job-tools-heading">Job tools</th>{visibleColumns.map((column) => <th key={column}>{label(column)}</th>)}</tr></thead>
                <tbody>
                  {filteredRows.map((row) => (
                    <tr key={text(row.job_record_id)}>
                      <td className="job-tools-cell">
                        <button className="table-action-button" type="button" onClick={() => setIntelligenceJob(row)}>
                          Official JD + resume
                        </button>
                      </td>
                      {visibleColumns.map((column) => (
                        <DiscoveryCell
                          key={column}
                          row={row}
                          column={column}
                          editable={run.editable_columns.includes(column)}
                          statuses={run.application_statuses}
                          onChange={(value) => updateCell(text(row.job_record_id), column, value)}
                        />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {!filteredRows.length && <div className="empty-table">No new or changed jobs match the current filters. Review Source Checks below for each selected company.</div>}
            </div>
            <p className="table-help">Publication dates remain unknown when the provider does not supply one. Only application status and notes can be edited.</p>

            <SourceChecks checks={run.source_checks} />
          </>
        ) : (
          <div className="empty-state">
            <div>↯</div>
            <h3>{companyMode ? "Rotate through selected official company sources" : "Use documented public ATS endpoints"}</h3>
            <p>{companyMode ? "The registry contains 210 unique companies. Select only the small batch you want to inspect today." : "Greenhouse, Lever, Workable, and SmartRecruiters are enabled. Other detected platforms remain explicit manual fallbacks."}</p>
          </div>
        )}
      </section>
    </main>
    {intelligenceJob && (
      <JobIntelligencePanel
        job={intelligenceJob}
        googleConnected={googleConnected}
        onClose={() => setIntelligenceJob(null)}
        onOfficialUrl={(url) => setIntelligenceJob((current) => current ? { ...current, official_url: url } : current)}
      />
    )}
    </>
  );
}

function Metric({ label: title, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return <article className={`metric-card ${accent ? "accent" : ""}`}><span>{title}</span><strong>{value.toLocaleString()}</strong></article>;
}

function DiscoveryCell({
  row,
  column,
  editable,
  statuses,
  onChange,
}: {
  row: JobRow;
  column: string;
  editable: boolean;
  statuses: string[];
  onChange: (value: Scalar) => void;
}) {
  const value = text(row[column]);
  if (editable && column === "application_status") {
    return <td><select value={value} onChange={(event) => onChange(event.target.value)}>{statuses.map((status) => <option key={status}>{status}</option>)}</select></td>;
  }
  if (editable && column === "notes") {
    return <td className="wide-cell"><textarea rows={3} value={value} placeholder="Add a review note…" onChange={(event) => onChange(event.target.value)} /></td>;
  }
  if (["official_url", "apply_url", "source_url"].includes(column)) {
    const linkText = column === "official_url" ? "Open official job" : column === "apply_url" ? "Open apply page" : "Open source";
    return <td>{value ? <a className="job-link" href={value} target="_blank" rel="noreferrer">{linkText} ↗</a> : <span className="muted">Not available</span>}</td>;
  }
  if (["provider", "experience_fit", "source_status", "application_status"].includes(column)) {
    return <td><span className={`value-chip ${value}`}>{value || "unknown"}</span></td>;
  }
  return <td className={["title", "description"].includes(column) ? "wide-cell" : ""}>{value || <span className="muted">—</span>}</td>;
}

function SourceChecks({ checks }: { checks: SourceCheckRow[] }) {
  return (
    <details className="source-checks" open>
      <summary>Source checks · {checks.length}</summary>
      <div className="table-wrap checks-table">
        <table>
          <thead><tr><th>Company</th><th>Provider</th><th>Strategy</th><th>Status</th><th>Found</th><th>Exported</th><th>Warning / fallback</th></tr></thead>
          <tbody>
            {checks.map((check, index) => (
              <tr key={`${check.company}-${check.provider}-${index}`}>
                <td>{check.company}</td>
                <td><span className="value-chip">{check.provider || "generic"}</span></td>
                <td>{check.strategy}</td>
                <td><span className={`value-chip ${check.status}`}>{check.status}</span></td>
                <td>{check.jobs_found}</td>
                <td>{check.jobs_exported}</td>
                <td className="wide-cell">{check.warning || check.fallback || <span className="muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
