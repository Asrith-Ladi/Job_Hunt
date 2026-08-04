export type Scalar = string | number | boolean | null;
export type JobRow = Record<string, Scalar>;

export interface GoogleStatus {
  connected: boolean;
  credentials_file_available: boolean;
  reconnect_required: boolean;
  message: string;
  redirect_uri: string;
}

export interface AppConfig {
  source_tabs: string[];
  sources: string[];
  labels_by_source: Record<string, string>;
  lookback_days: number;
  max_messages: number;
  target_experience_min_years: number;
  target_experience_max_years: number;
  include_unmatched_companies: boolean;
  strict_experience_filter: boolean;
  job_columns: string[];
  editable_columns: string[];
  application_statuses: string[];
  experience_fit_statuses: string[];
  drive_workspace_url: string;
  discovery_max_sources_per_run: number;
  supported_ats_providers: string[];
}

export interface SourceDetection {
  provider: string;
  identifier: string;
  confidence: number;
  official_public_api: boolean;
  adapter_ready: boolean;
  evidence: string;
  risk: string;
  fallback: string;
  region: string;
}

export interface CompanyRegistryEntry {
  company_id: string;
  company: string;
  category: string;
  sector: string;
  priority: string;
  careers_url: string;
  portal_url: string;
  source_type_label: string;
  source_identifier: string;
  public_feed_url: string;
  api_key_required: string;
  india_jobs: string;
  active: string;
  last_checked: string;
  verification_status: string;
  fallback: string;
  notes: string;
  detection: SourceDetection;
  adapter_ready: boolean;
}

export interface DiscoveryFiltersSettings {
  keyword: string;
  location: string;
  posted_within_days: number;
  include_unknown_dates: boolean;
  max_jobs_per_source: number;
  target_experience_min_years: number;
  target_experience_max_years: number;
  strict_experience_filter: boolean;
}

export interface ManualAtsSource {
  company: string;
  provider: "greenhouse" | "lever" | "workable" | "smartrecruiters";
  identifier: string;
  region: "global" | "eu";
  careers_url: string;
}

export interface SourceCheckRow extends Record<string, Scalar> {
  company: string;
  provider: string;
  strategy: string;
  status: string;
  jobs_found: number;
  jobs_exported: number;
  warning: string;
  fallback: string;
}

export interface DiscoveryRunArtifact extends RunArtifact {
  mode: "company_portals" | "ats_sources";
  source_checks: SourceCheckRow[];
}

export interface RunArtifact {
  run_id: string;
  run_started_at: string;
  file_name: string;
  drive_url: string;
  summary: Record<string, Scalar>;
  rows: JobRow[];
  job_columns: string[];
  editable_columns: string[];
  application_statuses: string[];
  experience_fit_statuses: string[];
}

export interface RunSettings {
  sources: string[];
  labels_by_source: Record<string, string>;
  gmail_query: string;
  company_allowlist: string;
  include_unmatched_companies: boolean;
  lookback_days: number;
  max_messages: number;
  target_experience_min_years: number;
  target_experience_max_years: number;
  strict_experience_filter: boolean;
  override_query: boolean;
}

export interface NetworkConnectionRow {
  connection_id: string;
  name: string;
  first_name: string;
  current_company: string;
  company: string;
  position: string;
  email_address: string;
  linkedin_profile: string;
  connected_on: string;
  registry_company: string;
  registry_category: string;
  referral_status: string;
  match_method: string;
  official_careers_page: string;
  direct_job_portal: string;
  relevance_score: number;
  category: string;
  recommended: boolean;
  leadership: boolean;
  relevance_reason: string;
  profile_review_message: string;
}

export interface NetworkConnectionsResponse {
  rows: NetworkConnectionRow[];
  total_matching: number;
  offset: number;
  limit: number;
  all_connections: number;
  all_profiles: number;
  email_connections: number;
  recommended_profiles: number;
  leadership_profiles: number;
  categories: string[];
  target_roles: string;
  source: "offline_linkedin_export";
}

export interface JobIntelligenceStatus {
  openai_configured: boolean;
  model: string;
  configuration_source: string;
  drive_connected: boolean;
  drive_backed: boolean;
  baseline_resume_configured: boolean;
  baseline_resume_name: string;
  baseline_resume_sha256: string;
  baseline_uploaded_at: string;
  baseline_drive_url: string;
  baseline_immutable: boolean;
  reference_documents: Array<{
    original_name: string;
    sha256: string;
    uploaded_at: string;
    drive_url: string;
  }>;
  reference_document_count: number;
  library_url: string;
  message: string;
  manual_only: boolean;
  contact_data_sent_to_openai: boolean;
}

export interface EligibilityAssessment {
  score: number;
  band: string;
  confidence: string;
  matched_skills: string[];
  gaps: string[];
  experience_reason: string;
  components: string;
}

export interface OfficialJobCandidate {
  official_job_id: string;
  company: string;
  title: string;
  location: string;
  experience_text: string;
  experience_min: number | null;
  experience_max: number | null;
  workplace_type: string;
  employment_type: string;
  active_status: string;
  requisition_id: string;
  published_at: string;
  official_url: string;
  description_summary: string;
  required_skills: string[];
  preferred_skills: string[];
  evidence_confidence: string;
  source_notes: string;
  official_match_status: string;
  official_match_score: number;
  official_match_reason: string;
  eligibility: EligibilityAssessment;
}

export interface JobAnalysis {
  analysis_id: string;
  status: "completed" | "no_official_match";
  job: Record<string, Scalar>;
  candidates: OfficialJobCandidate[];
  verified_at: string;
  model: string;
  cached: boolean;
  research_stats: Record<string, Scalar>;
  baseline_resume_configured: boolean;
  privacy: {
    gmail_content_sent: boolean;
    contact_data_sent: boolean;
    connection_data_sent: boolean;
  };
}

export type GeneratedArtifactKind = "resume_docx" | "resume_pdf" | "cover_letter";

export interface GeneratedArtifact {
  artifact_id: string;
  kind: GeneratedArtifactKind;
  file_name: string;
  mime_type: string;
  drive_url: string;
  folder_url: string;
  download_url: string;
}

export interface GeneratedDocumentSet {
  generation_id: string;
  generated_at: string;
  artifacts: GeneratedArtifact[];
  model: string;
  plan_cached: boolean;
  change_notes: string[];
  keyword_alignment: string[];
  reference_points_used: string[];
  warnings: string[];
  requires_user_review: boolean;
  baseline_unchanged: boolean;
}
