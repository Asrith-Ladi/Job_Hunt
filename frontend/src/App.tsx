import { useEffect, useMemo, useState } from "react";
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
  GoogleStatus,
  RunArtifact,
  RunSettings,
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

type ProductTab = "run_setup" | "job_queue" | "network_reviews";
type Notice = { kind: "success" | "error" | "info"; text: string };

function tabFromLocation(): ProductTab {
  const requested = new URLSearchParams(window.location.search).get("tab");
  return requested === "job_queue" || requested === "network_reviews" ? requested : "run_setup";
}

function summaryNumber(value: Scalar | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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

const EMPTY_DISCOVERY_SETTINGS: DiscoveryFiltersSettings = {
  keyword: "",
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
  const [setup, setSetup] = useState<RunSetupState>(EMPTY_SETUP);
  const [runs, setRuns] = useState<WorkspaceRuns>(EMPTY_RUNS);
  const [dirtySources, setDirtySources] = useState<Set<WorkspaceSource>>(new Set());
  const [runningSource, setRunningSource] = useState<WorkspaceSource | "">("");
  const [outcomes, setOutcomes] = useState<Partial<Record<WorkspaceSource, SourceOutcome>>>({});
  const [saving, setSaving] = useState(false);
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
          api.latestRun(),
          api.latestDiscoveryRun("company_portals"),
          api.latestDiscoveryRun("ats_sources"),
        ] as const);
        const [googleResult, registryResult, gmailResult, companyResult, atsResult] = startupResults;
        if (googleResult.status === "fulfilled") setGoogle(googleResult.value);
        if (registryResult.status === "fulfilled") setRegistry(registryResult.value.companies);
        setRuns({
          gmail: gmailResult.status === "fulfilled" ? gmailResult.value.run : null,
          company_portals: companyResult.status === "fulfilled" ? companyResult.value.run : null,
          ats_sources: atsResult.status === "fulfilled" ? atsResult.value.run : null,
        });

        const unavailable = [
          googleResult.status === "rejected" ? "Google status" : "",
          registryResult.status === "rejected" ? "company registry" : "",
          gmailResult.status === "rejected" ? "Gmail run" : "",
          companyResult.status === "rejected" ? "Company Portal run" : "",
          atsResult.status === "rejected" ? "ATS run" : "",
        ].filter(Boolean);
        if (unavailable.length) {
          setNotice({
            kind: "info",
            text: `${unavailable.join(", ")} could not be loaded. The available workspace remains usable.`,
          });
        }
      })
      .catch((error: Error) => {
        setNotice({ kind: "error", text: `The application configuration could not be loaded: ${error.message}` });
      })
      .finally(() => setLoading(false));
  }, []);

  const queueCount = useMemo(() => flattenRuns(runs).length, [runs]);
  const currentRunCount = useMemo(() => Object.values(runs).filter(Boolean).length, [runs]);

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

  const validateSetup = (): string => {
    if (!setup.enabledSources.length) return "Select at least one source to run.";
    if (setup.enabledSources.includes("gmail") && !setup.gmail.sources.length) {
      return "Choose LinkedIn, Naukri, or both for the Gmail source.";
    }
    if (setup.enabledSources.includes("company_portals") && !setup.companyIds.length) {
      return "Select at least one company for the Company Portal run.";
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
    return "";
  };

  const runSelectedSources = async () => {
    const validation = validateSetup();
    if (validation) {
      setNotice({ kind: "error", text: validation });
      return;
    }
    if (!google?.connected) {
      setNotice({ kind: "error", text: "Connect Google before creating Drive run artifacts." });
      return;
    }
    const dirtySelected = setup.enabledSources.some((source) => dirtySources.has(source));
    if (dirtySelected && !window.confirm("Running selected sources will replace their unsaved on-screen edits. Continue?")) return;

    const succeeded: WorkspaceSource[] = [];
    const failed: WorkspaceSource[] = [];
    setNotice({ kind: "info", text: "Running each selected source independently and preserving completed results…" });

    for (const source of setup.enabledSources) {
      setRunningSource(source);
      setOutcomes((current) => ({ ...current, [source]: { status: "running", message: "Running" } }));
      try {
        let run: RunArtifact | DiscoveryRunArtifact;
        if (source === "gmail") {
          run = (await api.runGmail(setup.gmail)).run;
        } else if (source === "company_portals") {
          run = (await api.runDiscovery(source, setup.companyIds, [], setup.discovery)).run;
        } else {
          run = (await api.runDiscovery(source, setup.atsCompanyIds, setup.manualAtsSources, setup.discovery)).run;
        }
        setRuns((current) => ({ ...current, [source]: run }));
        setDirtySources((current) => {
          const next = new Set(current);
          next.delete(source);
          return next;
        });
        succeeded.push(source);
        const currentMatches = summaryNumber(
          run.summary.jobs_after_deduplication,
          run.rows.length,
        );
        const newOrChanged = summaryNumber(
          run.summary.jobs_new_or_changed_this_run,
          run.rows.length,
        );
        setOutcomes((current) => ({
          ...current,
          [source]: {
            status: "success",
            message: source === "gmail"
              ? `${run.rows.length} rows ready`
              : `${currentMatches} matches · ${newOrChanged} new/changed`,
          },
        }));
      } catch (error) {
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
        text: `${succeeded.map((source) => SOURCE_LABELS[source]).join(", ")} completed${failed.length ? `; ${failed.map((source) => SOURCE_LABELS[source]).join(", ")} needs attention.` : ". The unified queue is ready."}`,
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
    setDirtySources((current) => new Set(current).add(item.source));
  };

  const saveChangedSources = async () => {
    if (!dirtySources.size) return;
    setSaving(true);
    const saved: WorkspaceSource[] = [];
    const failed: WorkspaceSource[] = [];
    for (const source of Array.from(dirtySources)) {
      const run = runs[source];
      if (!run) continue;
      try {
        const next = source === "gmail"
          ? (await api.saveRows(run.run_id, run.rows)).run
          : (await api.saveDiscoveryRows(source, run.run_id, run.rows)).run;
        setRuns((current) => ({ ...current, [source]: next }));
        saved.push(source);
      } catch {
        failed.push(source);
      }
    }
    setDirtySources((current) => {
      const next = new Set(current);
      saved.forEach((source) => next.delete(source));
      return next;
    });
    setSaving(false);
    setNotice({
      kind: failed.length ? "info" : "success",
      text: failed.length
        ? `${saved.length} source workbook${saved.length === 1 ? "" : "s"} saved; ${failed.map((source) => SOURCE_LABELS[source]).join(", ")} could not be updated.`
        : `${saved.length} source workbook${saved.length === 1 ? "" : "s"} updated locally and in Drive.`,
    });
  };

  if (loading) {
    return (
      <main className="loading-screen premium-loading">
        <div className="brand-mark">JH</div>
        <div><strong>Preparing your workspace</strong><span>Loading Drive state, source registry, and current queues…</span></div>
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

  return (
    <div className="app app-shell">
      <aside className="app-sidebar">
        <div className="brand sidebar-brand">
          <div className="brand-mark">JH</div>
          <div><p className="eyebrow">Personal workspace</p><h1>Job Hunt</h1></div>
        </div>

        <nav className="product-nav" aria-label="Primary navigation">
          <button className={activeTab === "run_setup" ? "active" : ""} type="button" onClick={() => navigateTo("run_setup")}>
            <span className="nav-index">01</span><span><strong>Run Setup</strong><small>Choose and configure sources</small></span>
          </button>
          <button className={activeTab === "job_queue" ? "active" : ""} type="button" onClick={() => navigateTo("job_queue")}>
            <span className="nav-index">02</span><span><strong>Job Queue</strong><small>{queueCount ? `${queueCount} source records` : "Unified review workspace"}</small></span>
          </button>
          <button className={activeTab === "network_reviews" ? "active" : ""} type="button" onClick={() => navigateTo("network_reviews")}>
            <span className="nav-index">03</span><span><strong>Network</strong><small>Reviewers and referral context</small></span>
          </button>
        </nav>

        <div className="sidebar-run-status">
          <small>Current workspace</small>
          <strong>{currentRunCount} source run{currentRunCount === 1 ? "" : "s"}</strong>
          <span>{queueCount} preserved job record{queueCount === 1 ? "" : "s"}</span>
          <button type="button" onClick={() => navigateTo("run_setup")}>Start another focused run →</button>
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
            <p className="eyebrow">{activeTab === "run_setup" ? "Discovery control" : activeTab === "job_queue" ? "Daily application workflow" : "Offline LinkedIn export"}</p>
            <strong>{activeTab === "run_setup" ? "Run Setup" : activeTab === "job_queue" ? "Job Queue" : "Network Reviews"}</strong>
          </div>
          <div className="topbar-actions">
            <span className="privacy-pill">Private · manual actions only</span>
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
            value={setup}
            onChange={setSetup}
            onRun={runSelectedSources}
            onConnectGoogle={connectGoogle}
            runningSource={runningSource}
            outcomes={outcomes}
          />
        ) : activeTab === "job_queue" ? (
          <JobQueueTab
            config={config}
            runs={runs}
            dirtySources={dirtySources}
            saving={saving}
            onSave={saveChangedSources}
            onUpdate={updateQueueRow}
            onOpenJob={setSelectedJob}
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
          googleConnected={Boolean(google?.connected)}
          onClose={() => setSelectedJob(null)}
          onOfficialUrl={(url) => {
            updateQueueRow(selectedJob, "official_url", url);
            setSelectedJob((current) => current ? { ...current, row: { ...current.row, official_url: url } } : null);
          }}
        />
      )}
    </div>
  );
}

export default App;
