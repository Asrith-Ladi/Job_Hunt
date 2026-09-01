import type {
  AIUsageReport,
  ApplicationPackageResult,
  AppConfig,
  ConfirmedSkillEvidence,
  DiscoveryFiltersSettings,
  DiscoveryRunArtifact,
  GoogleStatus,
  GeneratedArtifactKind,
  GeneratedDocumentSet,
  GmailRunHistoryEntry,
  JobAnalysis,
  JobIntelligenceStatus,
  JobRow,
  ManualAtsSource,
  NetworkConnectionsResponse,
  RegistryResponse,
  RunArtifact,
  RunSettings,
  ApplicationsResponse,
  ReferralCandidate,
  SavedApplication,
  SearchProgress,
} from "./types";

export type DiscoveryMode = "company_portals" | "ats_sources";

function discoveryBase(mode: DiscoveryMode): string {
  return mode === "company_portals" ? "/api/company-portals" : "/api/ats-sources";
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok) {
    if (
      (response.status === 404 || response.status === 405) &&
      url.startsWith("/api/search/") &&
      !url.startsWith("/api/search/progress/")
    ) {
      throw new Error(
        "The UI and backend versions do not match. Restart FastAPI, then refresh this page.",
      );
    }
    let message = `Request failed (${response.status})`;
    try {
      if (!contentType.includes("application/json")) throw new Error("Non-JSON response");
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-only message when the response is not JSON.
    }
    throw new Error(message);
  }
  if (!contentType.includes("application/json")) {
    throw new Error(
      "The running backend is out of date. Restart FastAPI, then refresh this page.",
    );
  }
  return (await response.json()) as T;
}

async function uploadRequest<T>(url: string, body: FormData): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "include",
    body,
  });
  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      if (!contentType.includes("application/json")) throw new Error("Non-JSON response");
      const value = (await response.json()) as { detail?: string };
      if (value.detail) message = value.detail;
    } catch {
      // Keep the status-only message when the response is not JSON.
    }
    throw new Error(message);
  }
  if (!contentType.includes("application/json")) {
    throw new Error("The running backend is out of date. Restart FastAPI, then refresh this page.");
  }
  return (await response.json()) as T;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),
  googleStatus: () => request<GoogleStatus>("/api/auth/google/status"),
  startGoogle: () =>
    request<{ authorization_url: string }>("/api/auth/google/start", {
      method: "POST",
    }),
  gmailRunHistory: () => request<{ runs: GmailRunHistoryEntry[] }>("/api/gmail/runs"),
  gmailRun: (runId: string) =>
    request<{ run: RunArtifact }>(`/api/gmail/runs/${encodeURIComponent(runId)}`),
  searchGmail: (settings: RunSettings, progressId = "") =>
    request<{ run: RunArtifact; progress?: SearchProgress }>("/api/search/gmail", {
      method: "POST",
      headers: progressId ? { "X-Job-Hunt-Progress-ID": progressId } : undefined,
      body: JSON.stringify({
        sources: settings.sources,
        labels_by_source: settings.labels_by_source,
        gmail_query: settings.override_query ? settings.gmail_query : "",
        company_allowlist: settings.company_allowlist
          .split(/\r?\n/)
          .map((item) => item.trim())
          .filter(Boolean),
        include_unmatched_companies: settings.include_unmatched_companies,
        lookback_days: settings.lookback_days,
        max_messages: settings.max_messages,
        target_experience_min_years: settings.target_experience_min_years,
        target_experience_max_years: settings.target_experience_max_years,
        strict_experience_filter: settings.strict_experience_filter,
      }),
    }),
  jobIntelligenceStatus: () =>
    request<JobIntelligenceStatus>("/api/job-intelligence/status"),
  aiUsage: (limit = 20) =>
    request<AIUsageReport>(`/api/job-intelligence/usage?limit=${encodeURIComponent(limit)}`),
  uploadBaselineResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return uploadRequest<JobIntelligenceStatus>(
      "/api/job-intelligence/baseline-resume",
      form,
    );
  },
  uploadReferenceDocuments: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return uploadRequest<JobIntelligenceStatus>(
      "/api/job-intelligence/reference-documents",
      form,
    );
  },
  analyzeJob: (job: JobRow, refresh = false) =>
    request<{ analysis: JobAnalysis }>("/api/job-intelligence/analyze", {
      method: "POST",
      body: JSON.stringify({
        refresh,
        job: {
          job_record_id: String(job.job_record_id ?? ""),
          company: String(job.company ?? ""),
          title: String(job.title ?? ""),
          location: String(job.location ?? ""),
          experience_text: String(job.experience_text ?? job.years_of_experience ?? ""),
          official_url: String(job.official_url ?? ""),
        },
      }),
    }),
  generateDocuments: (options: {
    analysisId: string;
    officialJobId: string;
    outputs: GeneratedArtifactKind[];
    confirmedSkillEvidence?: ConfirmedSkillEvidence[];
    refreshPlan?: boolean;
  }) =>
    request<{ generation: GeneratedDocumentSet }>("/api/job-intelligence/resumes", {
      method: "POST",
      body: JSON.stringify({
        analysis_id: options.analysisId,
        official_job_id: options.officialJobId,
        outputs: options.outputs,
        confirmed_skill_evidence: options.confirmedSkillEvidence ?? [],
        refresh_plan: options.refreshPlan ?? false,
      }),
    }),
  finalizeApplicationPackage: (options: {
    analysisId: string;
    officialJobId: string;
    generationId: string;
    source: "gmail" | "company_portals" | "ats_sources";
    row: JobRow;
    referralCandidates: ReferralCandidate[];
  }) => request<{
    package: ApplicationPackageResult;
    application: SavedApplication;
    count: number;
    drive_url: string;
  }>("/api/job-intelligence/apply", {
    method: "POST",
    body: JSON.stringify({
      analysis_id: options.analysisId,
      official_job_id: options.officialJobId,
      generation_id: options.generationId,
      source: options.source,
      row: options.row,
      referral_candidates: options.referralCandidates,
    }),
  }),
  registry: () => request<RegistryResponse>("/api/registry/companies"),
  applications: () => request<ApplicationsResponse>("/api/applications"),
  saveApplication: (
    source: "gmail" | "company_portals" | "ats_sources",
    row: JobRow,
    referralCandidates: ReferralCandidate[],
  ) => request<{ application: SavedApplication; count: number; drive_url: string }>(
    "/api/applications",
    {
      method: "PUT",
      body: JSON.stringify({
        source,
        row,
        referral_candidates: referralCandidates,
      }),
    },
  ),
  searchDiscovery: (
    mode: DiscoveryMode,
    companyIds: string[],
    manualSources: ManualAtsSource[],
    filters: DiscoveryFiltersSettings,
    progressId = "",
  ) =>
    request<{ run: DiscoveryRunArtifact; progress?: SearchProgress }>(`/api/search/${mode === "company_portals" ? "company-portals" : "ats-sources"}`, {
      method: "POST",
      headers: progressId ? { "X-Job-Hunt-Progress-ID": progressId } : undefined,
      body: JSON.stringify({
        company_ids: companyIds,
        manual_sources: manualSources,
        filters,
      }),
    }),
  searchProgress: (progressId: string) =>
    request<{ progress: SearchProgress }>(`/api/search/progress/${encodeURIComponent(progressId)}`),
  discoveryDownloadUrl: (mode: DiscoveryMode, runId: string) =>
    `${discoveryBase(mode)}/runs/${encodeURIComponent(runId)}/download`,
  networkConnections: (options: {
    query: string;
    category: string;
    recommendedOnly: boolean;
    leadershipOnly: boolean;
    targetRoles: string;
    offset: number;
    limit: number;
  }) => {
    const query = new URLSearchParams({
      q: options.query,
      category: options.category,
      recommended_only: String(options.recommendedOnly),
      leadership_only: String(options.leadershipOnly),
      target_roles: options.targetRoles,
      offset: String(options.offset),
      limit: String(options.limit),
    });
    return request<NetworkConnectionsResponse>(`/api/network/connections?${query}`);
  },
};
