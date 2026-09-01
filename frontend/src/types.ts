export type Scalar = string | number | boolean | null;
export type JobRow = Record<string, Scalar>;

export interface ReferralCandidate {
  name: string;
  position: string;
  profile_url: string;
  message: string;
}

export interface SavedApplication {
  application_id: string;
  source: "gmail" | "company_portals" | "ats_sources";
  source_record_id: string;
  saved_at: string;
  updated_at: string;
  row: JobRow;
  referral_candidates: ReferralCandidate[];
}

export interface ApplicationsResponse {
  applications: SavedApplication[];
  count: number;
  updated_at: string;
  drive_url: string;
}

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

export interface RegistryStatus {
  sync_status: "drive_current" | "drive_refreshed" | "drive_seeded" | "local_fallback";
  source: "google_drive" | "local_cache";
  warning: string;
  drive_url: string;
  drive_modified_time: string;
  synced_at: string;
}

export interface RegistryResponse {
  companies: CompanyRegistryEntry[];
  count: number;
  supported_ats_providers: string[];
  registry_status: RegistryStatus;
}

export interface DiscoveryFiltersSettings {
  keyword: string;
  capability_keywords: string;
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

export interface SearchProgressEvent {
  stage: string;
  message: string;
  current_item: string;
  completed_items: number;
  total_items: number;
  matches_found: number;
  at: string;
}

export interface SearchProgress {
  progress_id: string;
  source: "gmail" | "company_portals" | "ats_sources";
  status: "running" | "completed" | "failed";
  stage: string;
  message: string;
  current_item: string;
  completed_items: number;
  total_items: number;
  matches_found: number;
  started_at: string;
  updated_at: string;
  recent_events: SearchProgressEvent[];
}

export interface RunArtifact {
  run_id: string;
  run_started_at: string;
  file_name: string;
  drive_url: string;
  historical?: boolean;
  review_only?: boolean;
  transient?: boolean;
  summary: Record<string, Scalar>;
  rows: JobRow[];
  referral_candidates?: Record<string, ReferralCandidate[]>;
  job_columns: string[];
  editable_columns: string[];
  application_statuses: string[];
  experience_fit_statuses: string[];
}

export interface GmailRunHistoryEntry {
  run_id: string;
  run_started_at: string;
  file_name: string;
  drive_url: string;
  rows_exported: number;
  messages_read: number;
  unique_jobs: number;
  unchanged_jobs: number;
  status: string;
  is_current: boolean;
  loadable: boolean;
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
  confirmed_skill_evidence: ConfirmedSkillEvidence[];
  confirmed_skill_evidence_count: number;
  library_url: string;
  message: string;
  manual_only: boolean;
  contact_data_sent_to_openai: boolean;
  ai_usage?: AIUsageReport;
}

export interface AIUsageTotals {
  api_calls: number;
  calculated_cost_usd: number;
  unpriced_calls: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  web_search_calls: number;
}

export interface AIUsageEvent {
  event_id: string;
  recorded_at: string;
  operation: string;
  operation_label: string;
  model: string;
  job_record_id?: string;
  official_job_id?: string;
  company?: string;
  title?: string;
  input_tokens: number;
  cached_input_tokens: number;
  cache_write_tokens: number;
  uncached_input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  web_search_calls: number;
  token_cost_usd: number | null;
  web_search_cost_usd: number;
  calculated_cost_usd: number | null;
  currency: "USD";
  pricing_version: string;
  pricing_supported: boolean;
  long_context_pricing: boolean;
  usage_available: boolean;
}

export interface AIUsageEstimate {
  low_usd: number;
  estimated_usd: number;
  high_usd: number;
  web_search_possible: boolean;
  source: "initial_range" | "recent_average";
  sample_size: number;
  cache_cost_usd: number;
}

export interface AIActionUsage extends AIUsageTotals {
  events: AIUsageEvent[];
  cache_reused: boolean;
  expected_api_calls: number;
  tracking_complete: boolean;
  calculated_not_invoice: boolean;
}

export interface AIUsageReport {
  schema_version: number;
  currency: "USD";
  calculated_not_invoice: boolean;
  tracking_started_at: string;
  includes_calls_before_feature_enabled: boolean;
  all_time: AIUsageTotals;
  today: AIUsageTotals;
  current_month: AIUsageTotals;
  by_operation: Record<string, AIUsageTotals>;
  estimates: {
    official_job: AIUsageEstimate;
    resume_plan: AIUsageEstimate;
  };
  recent_events: AIUsageEvent[];
  pricing: {
    version: string;
    model: string;
    input_per_million_usd: number;
    cached_input_per_million_usd: number;
    cache_write_per_million_usd: number;
    output_per_million_usd: number;
    web_search_per_call_usd: number;
    source_url: string;
    web_search_source_url: string;
  };
  storage: {
    local_file: string;
    drive_path: string;
    drive_sync_enabled: boolean;
    last_drive_sync_succeeded: boolean | null;
    stores_prompts_or_documents: boolean;
  };
}

export interface EligibilityAssessment {
  score: number;
  band: string;
  confidence: string;
  matched_skills: string[];
  exact_matched_skills?: string[];
  equivalent_matched_skills?: string[];
  skill_match_evidence?: Record<string, {
    match_type: "exact" | "equivalent";
    evidence_ids: string[];
    evidence_kinds: string[];
  }>;
  missing_skills: string[];
  gaps: string[];
  experience_reason: string;
  components: string;
}

export interface ConfirmedSkillEvidence {
  skill: string;
  note: string;
  confirmed_at?: string;
  confirmed?: boolean;
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
  description?: string;
  description_summary: string;
  required_skills: string[];
  preferred_skills: string[];
  required_skill_evidence?: Record<string, string>;
  preferred_skill_evidence?: Record<string, string>;
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
  ai_usage?: AIActionUsage;
  warnings?: string[];
  baseline_resume_configured: boolean;
  eligibility_evidence_source?: "active_baseline_resume" | "verified_profile_snapshot";
  privacy: {
    gmail_content_sent: boolean;
    contact_data_sent: boolean;
    connection_data_sent: boolean;
    reference_evidence_sent: boolean;
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
  folder_path?: string;
  download_url: string;
}

export interface AtsAlignmentScore {
  score: number | null;
  band: string;
  required_coverage: number | null;
  preferred_coverage: number | null;
  matched_required: string[];
  missing_required: string[];
  matched_preferred: string[];
  missing_preferred: string[];
  breakdown: string;
}

export interface AtsAlignmentComparison {
  before: AtsAlignmentScore;
  after: AtsAlignmentScore | null;
  delta: number | null;
  methodology: string;
}

export interface GeneratedDocumentSet {
  generation_id: string;
  generated_at: string;
  artifacts: GeneratedArtifact[];
  model: string;
  plan_cached: boolean;
  ai_usage?: AIActionUsage;
  change_notes: string[];
  keyword_alignment: string[];
  confirmed_skills_added: string[];
  documented_equivalent_skills_added: string[];
  skill_placements: Array<{
    skill: string;
    target_skill_id: string;
    category: string;
  }>;
  experience_bullets_reframed: number;
  reference_points_used: string[];
  warnings: string[];
  requires_user_review: boolean;
  ats_alignment: AtsAlignmentComparison;
  baseline_unchanged: boolean;
}

export interface ApplicationPackageFile {
  kind: "job_description_document" | "job_description" | "application_details";
  file_name: string;
  sha256: string;
  drive_url: string;
  folder_url: string;
  folder_path: string;
}

export interface ApplicationPackageResult {
  application_status: "applied";
  applied_at: string;
  official_url: string;
  description_source:
    | "verified_official_description"
    | "collected_source_description"
    | "verified_description_summary"
    | "captured_official_json"
    | "captured_official_json_ld"
    | "captured_official_embedded_json"
    | "captured_official_html"
    | "captured_exact_ats_description";
  description_completeness: "full" | "partial" | "summary_only";
  full_description_available: boolean;
  capture_warning: string;
  folder_url: string;
  folder_path: string;
  files: ApplicationPackageFile[];
}
