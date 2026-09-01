import { useEffect, useMemo, useState } from "react";
import type {
  AppConfig,
  CompanyRegistryEntry,
  DiscoveryFiltersSettings,
  ManualAtsSource,
  RegistryStatus,
  RunSettings,
  SearchProgress,
} from "./types";
import { SOURCE_LABELS, type WorkspaceSource } from "./workspace";

export interface RunSetupState {
  enabledSources: WorkspaceSource[];
  gmail: RunSettings;
  discovery: DiscoveryFiltersSettings;
  companyIds: string[];
  atsCompanyIds: string[];
  manualAtsSources: ManualAtsSource[];
}

export interface SourceOutcome {
  status: "idle" | "running" | "success" | "error";
  message: string;
}

const SOURCE_COPY: Record<WorkspaceSource, { kicker: string; title: string; body: string }> = {
  gmail: {
    kicker: "Inbox signals",
    title: "Gmail alerts",
    body: "Read only the LinkedIn and Naukri labels you approve.",
  },
  company_portals: {
    kicker: "Official employers",
    title: "Company portals",
    body: "Check selected public career pages from your registry.",
  },
  ats_sources: {
    kicker: "Structured feeds",
    title: "ATS sources",
    body: "Use public Greenhouse, Lever, Workable, and SmartRecruiters postings.",
  },
};

const EMPTY_MANUAL: ManualAtsSource = {
  company: "",
  provider: "greenhouse",
  identifier: "",
  region: "global",
  careers_url: "",
};

const COMPANY_CATEGORY_ORDER = [
  "MNC",
  "Product Companies",
  "Startups",
  "Mid-Sized Companies",
  "Other Companies",
] as const;
const ALL_COMPANIES = "__all_companies__";
const SELECTED_COMPANIES = "__selected_companies__";

function sourceCount(source: WorkspaceSource, value: RunSetupState): string {
  if (source === "gmail") return `${value.gmail.sources.length} alert provider${value.gmail.sources.length === 1 ? "" : "s"}`;
  if (source === "company_portals") return `${value.companyIds.length} compan${value.companyIds.length === 1 ? "y" : "ies"}`;
  const count = value.atsCompanyIds.length + value.manualAtsSources.length;
  return `${count} public source${count === 1 ? "" : "s"}`;
}

const PROGRESS_STAGE_LABELS: Record<string, string> = {
  starting: "Starting",
  registry: "Loading registry",
  source_fetch: "Opening source",
  ats_api: "Reading public feed",
  career_page: "Inspecting careers page",
  source_fallback: "Trying fallback",
  source_complete: "Source checked",
  deduplicate: "Combining results",
  gmail_read: "Reading Gmail labels",
  gmail_fetch: "Downloading alert batches",
  gmail_parse: "Parsing alerts",
  gmail_deduplicate: "Removing duplicates",
  gmail_filter: "Applying filters",
  gmail_referrals: "Matching connections",
  completed: "Completed",
  failed: "Needs attention",
};

function elapsedText(startedAt: string, now: number): string {
  const started = Date.parse(startedAt);
  if (!Number.isFinite(started)) return "0s";
  const seconds = Math.max(0, Math.floor((now - started) / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${String(seconds % 60).padStart(2, "0")}s` : `${seconds}s`;
}

function SearchProgressPanel({ progress }: { progress: SearchProgress }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (progress.status !== "running") return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [progress.status, progress.progress_id]);

  const total = progress.total_items;
  const completed = Math.min(progress.completed_items, total || progress.completed_items);
  const percent = progress.status === "completed"
    ? 100
    : total > 0
      ? Math.min(96, Math.round((completed / total) * 100))
      : 8;
  const events = [...progress.recent_events].reverse().slice(0, 4);
  const source = SOURCE_LABELS[progress.source];

  return (
    <section className={`live-search-progress ${progress.status}`} role="status" aria-live="polite">
      <div className="progress-heading-row">
        <div className="progress-live-mark" aria-hidden="true"><span /></div>
        <div>
          <p className="eyebrow">Live search activity</p>
          <h3>{progress.status === "running" ? `Searching ${source}` : progress.message}</h3>
          <p>{progress.message}</p>
        </div>
        <span className={`progress-status-pill ${progress.status}`}>
          {PROGRESS_STAGE_LABELS[progress.stage] ?? progress.stage.replaceAll("_", " ")}
        </span>
      </div>

      <div className="progress-track" aria-label={`${percent}% complete`}>
        <span style={{ width: `${percent}%` }} />
      </div>

      <div className="progress-facts">
        <div><small>Currently checking</small><strong>{progress.current_item || "Finishing the search"}</strong></div>
        <div><small>Completed</small><strong>{total ? `${completed} / ${total}` : completed}</strong></div>
        <div><small>Matches so far</small><strong>{progress.matches_found}</strong></div>
        <div><small>Active time</small><strong>{elapsedText(progress.started_at, now)}</strong></div>
      </div>

      {events.length > 0 && (
        <div className="progress-event-strip" aria-label="Recent search steps">
          {events.map((event, index) => (
            <span className={index === 0 ? "current" : ""} key={`${event.at}:${event.stage}:${index}`}>
              <i aria-hidden="true" />{event.message}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function CompanySelector({
  rows,
  selected,
  onChange,
  maximum,
  emptyText,
}: {
  rows: CompanyRegistryEntry[];
  selected: string[];
  onChange: (value: string[]) => void;
  maximum: number;
  emptyText: string;
}) {
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState(ALL_COMPANIES);
  const needle = query.trim().toLocaleLowerCase();
  const categoryOptions = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((item) => counts.set(item.category, (counts.get(item.category) ?? 0) + 1));
    const ordered = COMPANY_CATEGORY_ORDER.filter((category) => counts.has(category));
    const additional = [...counts.keys()]
      .filter((category) => !COMPANY_CATEGORY_ORDER.some((known) => known === category))
      .sort((left, right) => left.localeCompare(right));
    return [...ordered, ...additional].map((category) => ({ category, count: counts.get(category) ?? 0 }));
  }, [rows]);
  const visible = rows.filter((item) => {
    const inCategory = categoryFilter === ALL_COMPANIES
      || (categoryFilter === SELECTED_COMPANIES && selected.includes(item.company_id))
      || item.category === categoryFilter;
    const matchesQuery = !needle || [item.company, item.sector, item.category, item.detection.provider]
      .some((value) => value.toLocaleLowerCase().includes(needle));
    return inCategory && matchesQuery;
  });

  const toggle = (companyId: string) => {
    if (selected.includes(companyId)) {
      onChange(selected.filter((item) => item !== companyId));
      return;
    }
    if (selected.length < maximum) onChange([...selected, companyId]);
  };

  return (
    <div className="registry-selector">
      <div className="registry-category-header">
        <strong>Company type</strong>
        <span>Selections stay active when you switch groups.</span>
      </div>
      <div className="registry-category-filters" role="group" aria-label="Filter companies by registry category">
        <button
          type="button"
          className={categoryFilter === ALL_COMPANIES ? "active" : ""}
          aria-pressed={categoryFilter === ALL_COMPANIES}
          onClick={() => setCategoryFilter(ALL_COMPANIES)}
        >
          <span>All</span><b>{rows.length}</b>
        </button>
        {categoryOptions.map(({ category, count }) => (
          <button
            type="button"
            className={categoryFilter === category ? "active" : ""}
            aria-pressed={categoryFilter === category}
            onClick={() => setCategoryFilter(category)}
            key={category}
          >
            <span>{category}</span><b>{count}</b>
          </button>
        ))}
        <button
          type="button"
          className={`selected-filter ${categoryFilter === SELECTED_COMPANIES ? "active" : ""}`}
          aria-pressed={categoryFilter === SELECTED_COMPANIES}
          onClick={() => setCategoryFilter(SELECTED_COMPANIES)}
        >
          <span>Selected</span><b>{selected.length}</b>
        </button>
      </div>
      <div className="registry-search-row">
        <label className="search-field">
          <span aria-hidden="true">⌕</span>
          <input value={query} placeholder="Find a company or provider" onChange={(event) => setQuery(event.target.value)} />
        </label>
        <span>{selected.length}/{maximum} selected</span>
      </div>
      <div className="registry-list premium-registry-list">
        {visible.map((item) => {
          const checked = selected.includes(item.company_id);
          const capped = !checked && selected.length >= maximum;
          return (
            <label className={`registry-item ${checked ? "selected" : ""} ${capped ? "disabled" : ""}`} key={item.company_id}>
              <input type="checkbox" checked={checked} disabled={capped} onChange={() => toggle(item.company_id)} />
              <span>
                <strong>{item.company}</strong>
                <small>{item.category} · {item.detection.provider || "generic"}</small>
              </span>
              <em className={item.adapter_ready ? "ready" : "fallback"}>{item.adapter_ready ? "API" : "Public"}</em>
            </label>
          );
        })}
        {!visible.length && (
          <p className="registry-empty">
            {categoryFilter === SELECTED_COMPANIES && !selected.length
              ? "No companies selected yet. Choose a company from any group to see it here."
              : needle
                ? "No companies match this type and search."
                : emptyText}
          </p>
        )}
      </div>
    </div>
  );
}

export default function RunSetupTab({
  config,
  googleConnected,
  registry,
  registryStatus,
  refreshingRegistry,
  value,
  onChange,
  onRun,
  onConnectGoogle,
  onRefreshRegistry,
  runningSource,
  progress,
  outcomes,
}: {
  config: AppConfig;
  googleConnected: boolean;
  registry: CompanyRegistryEntry[];
  registryStatus: RegistryStatus | null;
  refreshingRegistry: boolean;
  value: RunSetupState;
  onChange: (value: RunSetupState) => void;
  onRun: () => void;
  onConnectGoogle: () => void;
  onRefreshRegistry: () => void;
  runningSource: WorkspaceSource | "";
  progress: SearchProgress | null;
  outcomes: Partial<Record<WorkspaceSource, SourceOutcome>>;
}) {
  const [manualDraft, setManualDraft] = useState<ManualAtsSource>(EMPTY_MANUAL);
  const enabled = new Set(value.enabledSources);
  const running = Boolean(runningSource);
  const hasOfficialSources = enabled.has("company_portals") || enabled.has("ats_sources");
  const atsRegistry = useMemo(() => registry.filter((item) => item.adapter_ready), [registry]);

  const patch = (next: Partial<RunSetupState>) => onChange({ ...value, ...next });
  const toggleEnabled = (source: WorkspaceSource) => {
    patch({
      enabledSources: enabled.has(source)
        ? value.enabledSources.filter((item) => item !== source)
        : [...value.enabledSources, source],
    });
  };
  const updateExperience = (minimum: number, maximum: number) => {
    patch({
      gmail: {
        ...value.gmail,
        target_experience_min_years: minimum,
        target_experience_max_years: maximum,
      },
      discovery: {
        ...value.discovery,
        target_experience_min_years: minimum,
        target_experience_max_years: maximum,
      },
    });
  };
  const updateRecency = (days: number) => {
    patch({
      gmail: { ...value.gmail, lookback_days: days },
      discovery: { ...value.discovery, posted_within_days: days },
    });
  };
  const addManualSource = () => {
    if (!manualDraft.company.trim() || !manualDraft.identifier.trim()) return;
    const total = value.atsCompanyIds.length + value.manualAtsSources.length;
    if (total >= config.discovery_max_sources_per_run) return;
    patch({ manualAtsSources: [...value.manualAtsSources, { ...manualDraft }] });
    setManualDraft(EMPTY_MANUAL);
  };

  return (
    <main className="product-page run-setup-page">
      <section className="page-intro setup-intro">
        <div>
          <p className="eyebrow">Start a focused search</p>
          <h2>Find roles that fit your next move.</h2>
          <p>Pick your sources, set your preferences, and review every match before saving it.</p>
        </div>
        <div className="intro-action-stack">
          <span className={`readiness-pill ${googleConnected ? "ready" : "blocked"}`}>
            <span />{googleConnected ? "Sources ready" : "Google connection required"}
          </span>
          {googleConnected ? (
            <button className="primary-button premium-run-button" type="button" onClick={onRun} disabled={running || !value.enabledSources.length}>
              {running ? `Searching ${SOURCE_LABELS[runningSource as WorkspaceSource]}…` : `Search ${value.enabledSources.length || 0} selected source${value.enabledSources.length === 1 ? "" : "s"}`}
            </button>
          ) : (
            <button className="primary-button premium-run-button" type="button" onClick={onConnectGoogle}>Connect Google</button>
          )}
        </div>
      </section>

      {progress && (running || progress.status === "failed") && (
        <SearchProgressPanel progress={progress} />
      )}

      <div className="workflow-section-heading">
        <span>1</span><div><p className="eyebrow">Choose sources</p><h3>Where should we look?</h3></div>
      </div>
      <section className="source-selector-grid" aria-label="Sources to run">
        {(Object.keys(SOURCE_COPY) as WorkspaceSource[]).map((source) => {
          const copy = SOURCE_COPY[source];
          const outcome = outcomes[source];
          return (
            <article className={`source-selector-card ${enabled.has(source) ? "selected" : ""} ${runningSource === source ? "searching" : ""}`} key={source}>
              <label>
                <input type="checkbox" checked={enabled.has(source)} onChange={() => toggleEnabled(source)} disabled={running} />
                <span className="source-check-indicator">✓</span>
                <span className="source-selector-copy">
                  <small>{copy.kicker}</small>
                  <strong>{copy.title}</strong>
                  <p>{copy.body}</p>
                </span>
              </label>
              <footer>
                <span>{sourceCount(source, value)}</span>
                {outcome && outcome.status !== "idle" && <em className={outcome.status}>{outcome.message}</em>}
              </footer>
            </article>
          );
        })}
      </section>

      <section className="setup-block common-filters-block">
        <div className="section-title-row">
          <div>
            <span className="section-step">2</span>
            <p className="eyebrow">Your preferences</p>
            <h3>What role fits you?</h3>
          </div>
          <p>{hasOfficialSources
            ? "Add role titles and skills. Separate alternatives with commas."
            : "Choose how recent and experienced the roles should be."}</p>
        </div>
        <div className="common-filter-grid">
          {hasOfficialSources && (
            <label className="field wide-field">
              <span>Target role phrases <small>title match; comma-separated OR</small></span>
              <input value={value.discovery.keyword} placeholder="AI agent engineer, machine learning engineer, applied scientist" onChange={(event) => patch({ discovery: { ...value.discovery, keyword: event.target.value } })} />
            </label>
          )}
          {hasOfficialSources && (
            <label className="field wide-field">
              <span>Capabilities and JD terms <small>broad fallback; editable</small></span>
              <input value={value.discovery.capability_keywords} placeholder="agentic AI, LLM, RAG, MLOps" onChange={(event) => patch({ discovery: { ...value.discovery, capability_keywords: event.target.value } })} />
            </label>
          )}
          {hasOfficialSources && (
            <label className="field">
              <span>Location <small>optional</small></span>
              <input value={value.discovery.location} placeholder="Hyderabad, Bengaluru, remote" onChange={(event) => patch({ discovery: { ...value.discovery, location: event.target.value } })} />
            </label>
          )}
        </div>
        <details className="advanced advanced-search-filters">
          <summary>Advanced filters: recency, experience, and source limits</summary>
          <div className="common-filter-grid compact-grid">
            <label className="field">
              <span>Recent days</span>
              <input type="number" min="1" max="90" value={value.discovery.posted_within_days} onChange={(event) => updateRecency(Number(event.target.value))} />
            </label>
            <label className="field">
              <span>Minimum experience</span>
              <input type="number" min="0" step="0.5" value={value.discovery.target_experience_min_years} onChange={(event) => updateExperience(Number(event.target.value), value.discovery.target_experience_max_years)} />
            </label>
            <label className="field">
              <span>Maximum experience</span>
              <input type="number" min="0" step="0.5" value={value.discovery.target_experience_max_years} onChange={(event) => updateExperience(value.discovery.target_experience_min_years, Number(event.target.value))} />
            </label>
            {hasOfficialSources && (
              <label className="field">
                <span>Max jobs per official source</span>
                <input type="number" min="1" max="250" value={value.discovery.max_jobs_per_source} onChange={(event) => patch({ discovery: { ...value.discovery, max_jobs_per_source: Number(event.target.value) } })} />
              </label>
            )}
          </div>
          <div className="inline-options">
            {hasOfficialSources && (
            <label className="toggle-row">
              <input type="checkbox" checked={value.discovery.include_unknown_dates} onChange={(event) => patch({ discovery: { ...value.discovery, include_unknown_dates: event.target.checked } })} />
              <span>Keep official jobs with unknown publication dates</span>
            </label>
            )}
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={value.discovery.strict_experience_filter}
                onChange={(event) => patch({
                  discovery: { ...value.discovery, strict_experience_filter: event.target.checked },
                  gmail: { ...value.gmail, strict_experience_filter: event.target.checked },
                })}
              />
              <span>Exclude roles known outside the experience range</span>
            </label>
          </div>
        </details>
      </section>

      {enabled.has("gmail") && (
        <section className="setup-block source-config-block">
          <div className="section-title-row">
            <div><span className="section-step">3</span><p className="eyebrow">Gmail details</p><h3>Choose alert inboxes</h3></div>
            <span className="safe-badge">Read only</span>
          </div>
          <div className="gmail-source-grid">
            {(["linkedin", "naukri"] as const).map((source) => {
              const checked = value.gmail.sources.includes(source);
              return (
                <article className={`mailbox-source-card ${checked ? "selected" : ""}`} key={source}>
                  <label className="toggle-row">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => patch({
                        gmail: {
                          ...value.gmail,
                          sources: checked
                            ? value.gmail.sources.filter((item) => item !== source)
                            : [...value.gmail.sources, source],
                        },
                      })}
                    />
                    <span><strong>{source === "linkedin" ? "LinkedIn" : "Naukri"}</strong> alerts</span>
                  </label>
                  <label className="field">
                    <span>Gmail label</span>
                    <input value={value.gmail.labels_by_source[source] ?? ""} disabled={!checked} onChange={(event) => patch({ gmail: { ...value.gmail, labels_by_source: { ...value.gmail.labels_by_source, [source]: event.target.value } } })} />
                  </label>
                </article>
              );
            })}
          </div>
          <div className="common-filter-grid compact-grid">
            <label className="field">
              <span>Maximum emails</span>
              <input type="number" min="1" max="5000" value={value.gmail.max_messages} onChange={(event) => patch({ gmail: { ...value.gmail, max_messages: Number(event.target.value) } })} />
            </label>
            <label className="field wide-field">
              <span>Companies <small>optional, one per line</small></span>
              <textarea rows={2} value={value.gmail.company_allowlist} placeholder="Wipro&#10;Accenture&#10;Google" onChange={(event) => patch({ gmail: { ...value.gmail, company_allowlist: event.target.value } })} />
            </label>
          </div>
          <div className="inline-options">
            <label className="toggle-row">
              <input type="checkbox" checked={value.gmail.include_unmatched_companies} onChange={(event) => patch({ gmail: { ...value.gmail, include_unmatched_companies: event.target.checked } })} />
              <span>Keep unmatched or unknown companies</span>
            </label>
          </div>
          <details className="advanced compact-advanced">
            <summary>Advanced Gmail query</summary>
            <label className="toggle-row compact">
              <input type="checkbox" checked={value.gmail.override_query} onChange={(event) => patch({ gmail: { ...value.gmail, override_query: event.target.checked } })} />
              <span>Override the generated label and date query</span>
            </label>
            {value.gmail.override_query && <textarea rows={3} value={value.gmail.gmail_query} onChange={(event) => patch({ gmail: { ...value.gmail, gmail_query: event.target.value } })} />}
          </details>
        </section>
      )}

      {enabled.has("company_portals") && (
        <section className="setup-block source-config-block">
          <div className="section-title-row">
            <div><span className="section-step">3</span><p className="eyebrow">Company details</p><h3>Select official employers</h3></div>
            <span className="safe-badge">Maximum {config.discovery_max_sources_per_run}</span>
          </div>
          <div className={`registry-source-bar ${registryStatus?.warning ? "warning" : ""}`}>
            <div>
              <strong>{registryStatus?.source === "google_drive" ? "Drive registry" : "Validated registry cache"}</strong>
              <span>
                {registryStatus?.warning
                  || "Refresh after editing Company_Source_Registry.xlsx in Job Hunt / Source."}
              </span>
            </div>
            <div>
              {registryStatus?.drive_url && (
                <a href={registryStatus.drive_url} target="_blank" rel="noreferrer">Open in Drive ↗</a>
              )}
              <button type="button" onClick={onRefreshRegistry} disabled={refreshingRegistry}>
                {refreshingRegistry ? "Refreshing…" : "Refresh registry"}
              </button>
            </div>
          </div>
          <CompanySelector
            rows={registry}
            selected={value.companyIds}
            onChange={(companyIds) => patch({ companyIds })}
            maximum={config.discovery_max_sources_per_run}
            emptyText="No registry companies match this search."
          />
        </section>
      )}

      {enabled.has("ats_sources") && (
        <section className="setup-block source-config-block">
          <div className="section-title-row">
            <div><span className="section-step">3</span><p className="eyebrow">ATS details</p><h3>Select public job feeds</h3></div>
            <span className="safe-badge">No API keys</span>
          </div>
          <CompanySelector
            rows={atsRegistry}
            selected={value.atsCompanyIds}
            onChange={(atsCompanyIds) => patch({ atsCompanyIds })}
            maximum={Math.max(0, config.discovery_max_sources_per_run - value.manualAtsSources.length)}
            emptyText="No adapter-ready companies match this search."
          />
          <details className="manual-source premium-manual-source">
            <summary>Add a public ATS identifier manually</summary>
            <div className="common-filter-grid compact-grid">
              <label className="field"><span>Company</span><input value={manualDraft.company} onChange={(event) => setManualDraft({ ...manualDraft, company: event.target.value })} /></label>
              <label className="field"><span>Provider</span><select value={manualDraft.provider} onChange={(event) => setManualDraft({ ...manualDraft, provider: event.target.value as ManualAtsSource["provider"] })}><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="workable">Workable</option><option value="smartrecruiters">SmartRecruiters</option></select></label>
              <label className="field wide-field"><span>Board token, slug, subdomain, or company identifier</span><input value={manualDraft.identifier} onChange={(event) => setManualDraft({ ...manualDraft, identifier: event.target.value })} /></label>
              <label className="field"><span>Region</span><select value={manualDraft.region} onChange={(event) => setManualDraft({ ...manualDraft, region: event.target.value as ManualAtsSource["region"] })}><option value="global">Global</option><option value="eu">EU (Lever)</option></select></label>
            </div>
            <button className="secondary-button" type="button" onClick={addManualSource}>Add public source</button>
            {value.manualAtsSources.length > 0 && (
              <div className="manual-source-chips">
                {value.manualAtsSources.map((source, index) => (
                  <span className="manual-chip" key={`${source.provider}-${source.identifier}-${index}`}>
                    {source.company} · {source.provider}/{source.identifier}
                    <button type="button" aria-label={`Remove ${source.company}`} onClick={() => patch({ manualAtsSources: value.manualAtsSources.filter((_, itemIndex) => itemIndex !== index) })}>×</button>
                  </span>
                ))}
              </div>
            )}
          </details>
        </section>
      )}

    </main>
  );
}
