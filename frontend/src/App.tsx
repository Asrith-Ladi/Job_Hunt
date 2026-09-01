import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import JobIntelligencePanel from "./JobIntelligencePanel";
import JobQueueTab from "./JobQueueTab";
import NetworkReviewsTab from "./NetworkReviewsTab";
import RunSetupTab, { type RunSetupState, type SourceOutcome } from "./RunSetupTab";
import type {
  AppConfig,
  CompanyRegistryEntry,
  DiscoveryFiltersSettings,
  DiscoveryRunArtifact,
  GmailRunHistoryEntry,
  GoogleStatus,
  RegistryStatus,
  RunArtifact,
  RunSettings,
  SavedApplication,
  SearchProgress,
  Scalar,
} from "./types";
import {
  SOURCE_LABELS,
  flattenRuns,
  scalarText,
  type QueueItem,
  type WorkspaceRuns,
  type WorkspaceSource,
} from "./workspace";

type ProductTab = "run_setup" | "job_queue" | "applications" | "network_reviews";
type Notice = { kind: "success" | "error" | "info"; text: string };

const TAB_META: Record<ProductTab, { eyebrow: string; title: string }> = {
  run_setup: { eyebrow: "Find your next role", title: "Search" },
  job_queue: { eyebrow: "Fresh matches", title: "Results" },
  applications: { eyebrow: "Your job pipeline", title: "Applications" },
  network_reviews: { eyebrow: "People who can help", title: "Network" },
};

function tabFromLocation(): ProductTab {
  const requested = new URLSearchParams(window.location.search).get("tab");
  return requested === "job_queue" || requested === "applications" || requested === "network_reviews"
    ? requested
    : "run_setup";
}

function summaryNumber(value: Scalar | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function progressId(source: WorkspaceSource): string {
  const random = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${source}-${random}`;
}

const EMPTY_GMAIL_SETTINGS: RunSettings = {
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

const DEFAULT_ROLE_KEYWORDS = [
  "AI engineer",
  "AI/ML engineer",
  "machine learning engineer",
  "ML engineer",
  "AI agent engineer",
  "generative AI engineer",
  "applied AI engineer",
  "applied scientist",
  "data scientist",
  "MLOps engineer",
  "ML platform engineer",
  "NLP engineer",
  "computer vision engineer",
  "research engineer",
  "forward deployed engineer",
].join(", ");

const DEFAULT_CAPABILITY_KEYWORDS = [
  "artificial intelligence",
  "machine learning",
  "generative AI",
  "GenAI",
  "LLM",
  "large language model",
  "agentic AI",
  "AI agents",
  "RAG",
  "MLOps",
  "ML platform",
  "NLP",
  "natural language processing",
  "computer vision",
  "deep learning",
].join(", ");

const EMPTY_DISCOVERY_SETTINGS: DiscoveryFiltersSettings = {
  keyword: DEFAULT_ROLE_KEYWORDS,
  capability_keywords: DEFAULT_CAPABILITY_KEYWORDS,
  location: "",
  posted_within_days: 30,
  include_unknown_dates: true,
  max_jobs_per_source: 100,
  target_experience_min_years: 5,
  target_experience_max_years: 8,
  strict_experience_filter: false,
};

const EMPTY_SETUP: RunSetupState = {
  enabledSources: ["gmail"],
  gmail: EMPTY_GMAIL_SETTINGS,
  discovery: EMPTY_DISCOVERY_SETTINGS,
  companyIds: [],
  atsCompanyIds: [],
  manualAtsSources: [],
};

const EMPTY_RUNS: WorkspaceRuns = {
  gmail: null,
  company_portals: null,
  ats_sources: null,
};

function App() {
  const [activeTab, setActiveTab] = useState<ProductTab>(tabFromLocation);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [registry, setRegistry] = useState<CompanyRegistryEntry[]>([]);
  const [registryStatus, setRegistryStatus] = useState<RegistryStatus | null>(null);
  const [refreshingRegistry, setRefreshingRegistry] = useState(false);
  const [setup, setSetup] = useState<RunSetupState>(EMPTY_SETUP);
  const [runs, setRuns] = useState<WorkspaceRuns>(EMPTY_RUNS);
  const [savedApplications, setSavedApplications] = useState<SavedApplication[]>([]);
  const [gmailHistory, setGmailHistory] = useState<GmailRunHistoryEntry[]>([]);
  const [loadingHistoryRunId, setLoadingHistoryRunId] = useState("");
  const [runningSource, setRunningSource] = useState<WorkspaceSource | "">("");
  const [searchProgress, setSearchProgress] = useState<SearchProgress | null>(null);
  const activeProgressId = useRef("");
  const [outcomes, setOutcomes] = useState<Partial<Record<WorkspaceSource, SourceOutcome>>>({});
  const [savingJobIds, setSavingJobIds] = useState<Set<string>>(new Set());
  const [selectedJob, setSelectedJob] = useState<QueueItem | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const callbackState = new URLSearchParams(window.location.search).get("google");
    if (callbackState) {
      const callbackNotice: Notice = callbackState === "connected"
        ? { kind: "success", text: "Google connected successfully." }
        : callbackState === "denied"
          ? { kind: "info", text: "Google authorization was cancelled. No mailbox data was read." }
          : { kind: "error", text: "Google authorization could not be completed. Reconnect and try again." };
      setNotice(callbackNotice);
      const cleanUrl = new URL(window.location.href);
      cleanUrl.searchParams.delete("google");
      cleanUrl.searchParams.set("tab", activeTab);
      window.history.replaceState({}, "", `${cleanUrl.pathname}${cleanUrl.search}`);
    }

    api.config()
      .then(async (appConfig) => {
        setConfig(appConfig);
        setSetup((current) => ({
          ...current,
          gmail: {
            ...current.gmail,
            labels_by_source: appConfig.labels_by_source,
            lookback_days: appConfig.lookback_days,
            max_messages: appConfig.max_messages,
            target_experience_min_years: appConfig.target_experience_min_years,
            target_experience_max_years: appConfig.target_experience_max_years,
            include_unmatched_companies: appConfig.include_unmatched_companies,
            strict_experience_filter: appConfig.strict_experience_filter,
          },
          discovery: {
            ...current.discovery,
            posted_within_days: appConfig.lookback_days,
            target_experience_min_years: appConfig.target_experience_min_years,
            target_experience_max_years: appConfig.target_experience_max_years,
            strict_experience_filter: appConfig.strict_experience_filter,
          },
        }));

        const startupResults = await Promise.allSettled([
          api.googleStatus(),
          api.registry(),
          api.gmailRunHistory(),
          api.applications(),
        ] as const);
        const [
          googleResult,
          registryResult,
          gmailHistoryResult,
          applicationsResult,
        ] = startupResults;
        if (googleResult.status === "fulfilled") setGoogle(googleResult.value);
        if (registryResult.status === "fulfilled") {
          setRegistry(registryResult.value.companies);
          setRegistryStatus(registryResult.value.registry_status);
        }
        if (gmailHistoryResult.status === "fulfilled") setGmailHistory(gmailHistoryResult.value.runs);
        if (applicationsResult.status === "fulfilled") {
          setSavedApplications(applicationsResult.value.applications);
        }

        const unavailable = [
          googleResult.status === "rejected" ? "Google status" : "",
          registryResult.status === "rejected" ? "company registry" : "",
          gmailHistoryResult.status === "rejected" ? "Gmail run history" : "",
          applicationsResult.status === "rejected" ? "saved applications" : "",
        ].filter(Boolean);
        if (unavailable.length) {
          setNotice({
            kind: "info",
            text: `${unavailable.join(", ")} could not be loaded. The available workspace remains usable.`,
          });
        } else if (
          registryResult.status === "fulfilled"
          && registryResult.value.registry_status.warning
        ) {
          setNotice({ kind: "info", text: registryResult.value.registry_status.warning });
        }
      })
      .catch((error: Error) => {
        setNotice({ kind: "error", text: `The application configuration could not be loaded: ${error.message}` });
      })
      .finally(() => setLoading(false));
  }, []);

  const resultCount = useMemo(
    () => flattenRuns(runs, savedApplications)
      .filter((item) => item.runId !== "application_queue").length,
    [runs, savedApplications],
  );
  const currentSearchCount = useMemo(
    () => Object.values(runs).filter((run) => run?.transient).length,
    [runs],
  );

  const navigateTo = (tab: ProductTab) => {
    setActiveTab(tab);
    const url = new URL(window.location.href);
    url.searchParams.delete("google");
    url.searchParams.set("tab", tab);
    window.history.replaceState({}, "", `${url.pathname}${url.search}`);
  };

  const connectGoogle = async () => {
    try {
      setNotice(null);
      const response = await api.startGoogle();
      window.location.assign(response.authorization_url);
    } catch (error) {
      setNotice({ kind: "error", text: (error as Error).message });
    }
  };

  const refreshRegistry = async () => {
    setRefreshingRegistry(true);
    try {
      const response = await api.registry();
      const validIds = new Set(response.companies.map((company) => company.company_id));
      setRegistry(response.companies);
      setRegistryStatus(response.registry_status);
      setSetup((current) => ({
        ...current,
        companyIds: current.companyIds.filter((companyId) => validIds.has(companyId)),
        atsCompanyIds: current.atsCompanyIds.filter((companyId) => validIds.has(companyId)),
      }));
      setNotice({
        kind: response.registry_status.warning ? "info" : "success",
        text: response.registry_status.warning
          || `Company registry refreshed from Drive (${response.count} companies).`,
      });
    } catch (error) {
      setNotice({ kind: "error", text: (error as Error).message });
    } finally {
      setRefreshingRegistry(false);
    }
  };

  const validateSetup = (): string => {
    if (!setup.enabledSources.length) return "Select at least one source to search.";
    if (setup.enabledSources.includes("gmail") && !setup.gmail.sources.length) {
      return "Choose LinkedIn, Naukri, or both for the Gmail source.";
    }
    if (setup.enabledSources.includes("company_portals") && !setup.companyIds.length) {
      return "Select at least one company for the Company Portal search.";
    }
    if (
      setup.enabledSources.includes("ats_sources")
      && setup.atsCompanyIds.length + setup.manualAtsSources.length === 0
    ) {
      return "Select or add at least one public ATS source.";
    }
    if (setup.discovery.target_experience_max_years < setup.discovery.target_experience_min_years) {
      return "Maximum experience must be at least the minimum experience.";
    }
    if (setup.discovery.posted_within_days < 1 || setup.discovery.posted_within_days > 90) {
      return "Recent days must be between 1 and 90.";
    }
    return "";
  };

  const beginProgressPolling = (id: string, source: WorkspaceSource) => {
    const now = new Date().toISOString();
    activeProgressId.current = id;
    setSearchProgress({
      progress_id: id,
      source,
      status: "running",
      stage: "starting",
      message: `Preparing ${SOURCE_LABELS[source]} search.`,
      current_item: "Validating selected settings",
      completed_items: 0,
      total_items: 0,
      matches_found: 0,
      started_at: now,
      updated_at: now,
      recent_events: [],
    });

    const poll = async () => {
      while (activeProgressId.current === id) {
        try {
          const response = await api.searchProgress(id);
          if (activeProgressId.current === id) setSearchProgress(response.progress);
        } catch {
          // The POST may not have registered the progress ID yet; retry while active.
        }
        await new Promise((resolve) => window.setTimeout(resolve, 600));
      }
    };
    void poll();
  };

  const finishProgressPolling = (id: string, finalProgress?: SearchProgress) => {
    if (activeProgressId.current === id) activeProgressId.current = "";
    if (finalProgress) setSearchProgress(finalProgress);
  };

  const runSelectedSources = async () => {
    const validation = validateSetup();
    if (validation) {
      setNotice({ kind: "error", text: validation });
      return;
    }
    if (!google?.connected) {
      setNotice({ kind: "error", text: "Connect Google before reading Gmail or the Drive company registry." });
      return;
    }

    const succeeded: WorkspaceSource[] = [];
    const failed: WorkspaceSource[] = [];
    setNotice({ kind: "info", text: "Searching each selected source independently. Results stay temporary until you save or update a job." });

    for (const source of setup.enabledSources) {
      setRunningSource(source);
      setOutcomes((current) => ({ ...current, [source]: { status: "running", message: "Searching" } }));
      const activeId = progressId(source);
      beginProgressPolling(activeId, source);
      try {
        let run: RunArtifact | DiscoveryRunArtifact;
        let finalProgress: SearchProgress | undefined;
        if (source === "gmail") {
          const response = await api.searchGmail(setup.gmail, activeId);
          run = response.run;
          finalProgress = response.progress;
        } else if (source === "company_portals") {
          const response = await api.searchDiscovery(source, setup.companyIds, [], setup.discovery, activeId);
          run = response.run;
          finalProgress = response.progress;
        } else {
          const response = await api.searchDiscovery(source, setup.atsCompanyIds, setup.manualAtsSources, setup.discovery, activeId);
          run = response.run;
          finalProgress = response.progress;
        }
        finishProgressPolling(activeId, finalProgress);
        setRuns((current) => ({ ...current, [source]: run }));
        succeeded.push(source);
        const currentMatches = summaryNumber(
          run.summary.jobs_after_deduplication,
          run.rows.length,
        );
        const extracted = summaryNumber(
          run.summary.jobs_extracted_before_filters,
          currentMatches,
        );
        setOutcomes((current) => ({
          ...current,
          [source]: {
            status: "success",
            message: source === "gmail"
              ? `${currentMatches} temporary match${currentMatches === 1 ? "" : "es"}`
              : `${extracted} extracted → ${currentMatches} matched`,
          },
        }));
      } catch (error) {
        finishProgressPolling(activeId);
        try {
          const response = await api.searchProgress(activeId);
          setSearchProgress(response.progress);
        } catch {
          // Preserve the locally visible error when no progress snapshot exists.
        }
        failed.push(source);
        setOutcomes((current) => ({
          ...current,
          [source]: { status: "error", message: (error as Error).message },
        }));
      }
    }

    setRunningSource("");
    if (succeeded.length) {
      navigateTo("job_queue");
      setNotice({
        kind: failed.length ? "info" : "success",
        text: `${succeeded.map((source) => SOURCE_LABELS[source]).join(", ")} search completed${failed.length ? `; ${failed.map((source) => SOURCE_LABELS[source]).join(", ")} needs attention.` : ". Results are temporary until you save or update a job."}`,
      });
    } else {
      setNotice({ kind: "error", text: "No selected source completed. Review each source message and try again." });
    }
  };

  const updateQueueRow = (item: QueueItem, column: string, value: Scalar) => {
    setRuns((current) => {
      const run = current[item.source];
      if (!run || run.run_id !== item.runId) return current;
      const recordId = scalarText(item.row.job_record_id ?? item.row.external_job_id);
      const nextRows = run.rows.map((row) => {
        const candidateId = scalarText(row.job_record_id ?? row.external_job_id);
        return row === item.row || (recordId && candidateId === recordId)
          ? { ...row, [column]: value }
          : row;
      });
      return { ...current, [item.source]: { ...run, rows: nextRows } };
    });
    if (item.applicationId) {
      setSavedApplications((current) => current.map((application) => (
        application.application_id === item.applicationId
          ? { ...application, row: { ...application.row, [column]: value } }
          : application
      )));
    }
    setSelectedJob((current) => current?.id === item.id
      ? { ...current, row: { ...current.row, [column]: value } }
      : current);
  };

  const persistQueueRow = async (item: QueueItem, column: string, value: Scalar) => {
    const nextStatus = column === "application_status" ? scalarText(value) : "";
    if (
      ["applied", "interviewing", "offer"].includes(nextStatus)
      && !scalarText(item.row.job_description_drive_url)
    ) {
      setSelectedJob(item);
      setNotice({
        kind: "info",
        text: "Generate and review the application documents, then use ‘I applied — save JD & details’. This keeps every applied job linked to its Drive evidence package.",
      });
      return;
    }
    const nextRow = { ...item.row, [column]: value };
    updateQueueRow(item, column, value);
    setSavingJobIds((current) => new Set(current).add(item.id));
    try {
      const response = await api.saveApplication(item.source, nextRow, item.referralCandidates);
      setSavedApplications((current) => [
        response.application,
        ...current.filter(
          (application) => application.application_id !== response.application.application_id,
        ),
      ]);
      setNotice({
        kind: "success",
        text: column === "application_status"
          ? "Application status saved permanently in Drive."
          : "Job changes saved permanently in Drive.",
      });
    } catch (error) {
      setNotice({
        kind: "error",
        text: `The job remains on screen but was not saved: ${(error as Error).message}`,
      });
    } finally {
      setSavingJobIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
    }
  };

  const acceptAppliedApplication = (
    item: QueueItem,
    application: SavedApplication,
  ) => {
    setSavedApplications((current) => [
      application,
      ...current.filter(
        (candidate) => candidate.application_id !== application.application_id,
      ),
    ]);
    const recordId = scalarText(item.row.job_record_id ?? item.row.external_job_id);
    setRuns((current) => {
      const run = current[item.source];
      if (!run || run.run_id !== item.runId) return current;
      const rows = run.rows.map((row) => {
        const candidateId = scalarText(row.job_record_id ?? row.external_job_id);
        return row === item.row || (recordId && candidateId === recordId)
          ? { ...row, ...application.row }
          : row;
      });
      return { ...current, [item.source]: { ...run, rows } };
    });
    setSelectedJob((current) => current?.id === item.id
      ? {
          ...current,
          row: { ...current.row, ...application.row },
          referralCandidates: application.referral_candidates,
          persisted: true,
          applicationId: application.application_id,
        }
      : current);
    setNotice({
      kind: "success",
      text: "Application marked Applied. Its JD package is saved beside the generated resume in Drive.",
    });
  };

  const loadHistoricalGmailRun = async (runId: string) => {
    setLoadingHistoryRunId(runId);
    try {
      const historical = (await api.gmailRun(runId)).run;
      setRuns((current) => ({ ...current, gmail: historical }));
      navigateTo("job_queue");
      setNotice({
        kind: "success",
        text: historical.historical
          ? `${historical.file_name} loaded for review. New status and note changes save to the canonical application queue.`
          : `${historical.file_name} restored as the current Gmail run.`,
      });
    } catch (error) {
      setNotice({ kind: "error", text: (error as Error).message });
    } finally {
      setLoadingHistoryRunId("");
    }
  };

  if (loading) {
    return (
      <main className="loading-screen premium-loading">
        <div className="loading-brand" aria-hidden="true"><span>JH</span><i /><i /><i /></div>
        <div className="loading-copy"><p className="eyebrow">Career workspace</p><strong>Preparing Job Hunt</strong><span>Bringing your searches and applications together…</span></div>
      </main>
    );
  }

  if (!config) {
    return (
      <main className="loading-screen premium-loading startup-error">
        <div className="brand-mark">!</div>
        <div>
          <strong>Workspace configuration is unavailable</strong>
          <span>{notice?.text || "Check that the FastAPI service is running, then try again."}</span>
          <button className="primary-button" type="button" onClick={() => window.location.reload()}>Retry</button>
        </div>
      </main>
    );
  }

  const activeTabMeta = TAB_META[activeTab];

  return (
    <div className="app app-shell">
      <aside className="app-sidebar">
        <div className="brand sidebar-brand">
          <div className="brand-mark">JH</div>
          <div><p className="eyebrow">Career workspace</p><h1>Job Hunt</h1></div>
        </div>

        <nav className="product-nav" aria-label="Primary navigation">
          <button className={activeTab === "run_setup" ? "active" : ""} type="button" onClick={() => navigateTo("run_setup")}>
            <span className="nav-index">01</span><span><strong>Search</strong><small>Find matching roles</small></span>
          </button>
          <button className={activeTab === "job_queue" ? "active" : ""} type="button" onClick={() => navigateTo("job_queue")}>
            <span className="nav-index">02</span><span><strong>Results</strong><small>{resultCount ? `${resultCount} matches to review` : "Review new matches"}</small></span>
          </button>
          <button className={activeTab === "applications" ? "active" : ""} type="button" onClick={() => navigateTo("applications")}>
            <span className="nav-index">03</span><span><strong>Applications</strong><small>{savedApplications.length ? `${savedApplications.length} jobs in your pipeline` : "Track your progress"}</small></span>
          </button>
          <button className={activeTab === "network_reviews" ? "active" : ""} type="button" onClick={() => navigateTo("network_reviews")}>
            <span className="nav-index">04</span><span><strong>Network</strong><small>Find relevant connections</small></span>
          </button>
        </nav>

        <div className="sidebar-run-status">
          <small>Current workspace</small>
          <strong>{currentSearchCount} active search{currentSearchCount === 1 ? "" : "es"}</strong>
          <span>{savedApplications.length} permanently saved job{savedApplications.length === 1 ? "" : "s"}</span>
          <button type="button" onClick={() => navigateTo("run_setup")}>Start another search →</button>
          <button type="button" onClick={() => navigateTo("applications")}>Open applications →</button>
        </div>

        <div className={`sidebar-connection ${google?.connected ? "connected" : "disconnected"}`}>
          <span className="status-dot" />
          <div><strong>{google?.connected ? "Google connected" : "Google disconnected"}</strong><small>{google?.connected ? "Gmail read-only · Drive app files" : google?.message}</small></div>
          {!google?.connected && <button type="button" onClick={connectGoogle}>{google?.reconnect_required ? "Reconnect" : "Connect"}</button>}
        </div>
      </aside>

      <section className="app-content">
        <header className="content-topbar">
          <div>
            <p className="eyebrow">{activeTabMeta.eyebrow}</p>
            <strong>{activeTabMeta.title}</strong>
          </div>
          <div className="topbar-actions">
            <span className="privacy-pill">Private workspace</span>
            {config.drive_workspace_url && (
              <a href={config.drive_workspace_url} target="_blank" rel="noreferrer">
                <span className="drive-link-desktop">Open Drive workspace</span>
                <span className="drive-link-mobile">Drive</span> ↗
              </a>
            )}
          </div>
        </header>

        {notice && (
          <div className={`notice premium-notice ${notice.kind}`} role="status" aria-live="polite">
            <span>{notice.kind === "success" ? "✓" : notice.kind === "error" ? "!" : "i"}</span>
            <p>{notice.text}</p>
            <button type="button" aria-label="Dismiss message" onClick={() => setNotice(null)}>×</button>
          </div>
        )}

        {activeTab === "run_setup" ? (
          <RunSetupTab
            config={config}
            googleConnected={Boolean(google?.connected)}
            registry={registry}
            registryStatus={registryStatus}
            refreshingRegistry={refreshingRegistry}
            value={setup}
            onChange={setSetup}
            onRun={runSelectedSources}
            onConnectGoogle={connectGoogle}
            onRefreshRegistry={refreshRegistry}
            runningSource={runningSource}
            progress={searchProgress}
            outcomes={outcomes}
          />
        ) : activeTab === "job_queue" ? (
          <JobQueueTab
            key="results"
            mode="results"
            config={config}
            runs={runs}
            savedApplications={savedApplications}
            gmailHistory={gmailHistory}
            loadingHistoryRunId={loadingHistoryRunId}
            onUpdate={updateQueueRow}
            onPersist={persistQueueRow}
            savingJobIds={savingJobIds}
            onOpenJob={setSelectedJob}
            onLoadGmailRun={loadHistoricalGmailRun}
            onGoToSetup={() => navigateTo("run_setup")}
            onNotice={(text) => setNotice({ kind: "success", text })}
          />
        ) : activeTab === "applications" ? (
          <JobQueueTab
            key="applications"
            mode="applications"
            config={config}
            runs={runs}
            savedApplications={savedApplications}
            gmailHistory={gmailHistory}
            loadingHistoryRunId={loadingHistoryRunId}
            onUpdate={updateQueueRow}
            onPersist={persistQueueRow}
            savingJobIds={savingJobIds}
            onOpenJob={setSelectedJob}
            onLoadGmailRun={loadHistoricalGmailRun}
            onGoToSetup={() => navigateTo("run_setup")}
            onNotice={(text) => setNotice({ kind: "success", text })}
          />
        ) : (
          <NetworkReviewsTab onNotice={setNotice} />
        )}
      </section>

      {selectedJob && (
        <JobIntelligencePanel
          job={selectedJob.row}
          source={selectedJob.source}
          referralCandidates={selectedJob.referralCandidates}
          googleConnected={Boolean(google?.connected)}
          onClose={() => setSelectedJob(null)}
          onOfficialUrl={(url) => {
            void persistQueueRow(selectedJob, "official_url", url);
            setSelectedJob((current) => current ? { ...current, row: { ...current.row, official_url: url } } : null);
          }}
          onApplicationSaved={(application) => acceptAppliedApplication(selectedJob, application)}
        />
      )}
    </div>
  );
}

export default App;
