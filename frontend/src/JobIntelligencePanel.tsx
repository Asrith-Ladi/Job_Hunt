import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  AIActionUsage,
  AIUsageEstimate,
  AIUsageReport,
  ConfirmedSkillEvidence,
  GeneratedArtifact,
  GeneratedArtifactKind,
  GeneratedDocumentSet,
  JobAnalysis,
  JobIntelligenceStatus,
  JobRow,
  OfficialJobCandidate,
  Scalar,
} from "./types";

type EvidenceDraft = ConfirmedSkillEvidence & { confirmed: boolean };

function skillKey(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

const OUTPUT_LABELS: Record<GeneratedArtifactKind, string> = {
  resume_docx: "Tailored resume (DOCX)",
  resume_pdf: "Tailored resume (PDF)",
  cover_letter: "Cover letter (DOCX)",
};

function text(value: Scalar | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function usd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unavailable";
  if (value === 0) return "$0.0000";
  return `$${value < 0.01 ? value.toFixed(4) : value.toFixed(3)}`;
}

function tokenCount(value: number | undefined): string {
  return Math.max(0, value ?? 0).toLocaleString();
}

function estimateText(estimate: AIUsageEstimate | undefined): string {
  if (!estimate) return "Estimate loading...";
  return `${usd(estimate.low_usd)}-${usd(estimate.high_usd)}`;
}

function CostEstimate({
  estimate,
  area,
}: {
  estimate: AIUsageEstimate | undefined;
  area: string;
}) {
  return (
    <div className="ai-cost-estimate">
      <div>
        <small>Pre-run AI estimate</small>
        <strong>{estimateText(estimate)}</strong>
      </div>
      <p>
        {area}. A cache hit costs $0. Estimate source: {estimate?.source === "recent_average"
          ? `${estimate.sample_size} recent call${estimate.sample_size === 1 ? "" : "s"}`
          : "initial conservative range"}.
      </p>
    </div>
  );
}

function ActionCost({ usage }: { usage: AIActionUsage | undefined }) {
  if (!usage) return null;
  if (usage.cache_reused && usage.expected_api_calls === 0) {
    return (
      <div className="ai-action-cost cached">
        <strong>$0 new API cost</strong>
        <span>No Luna call was needed; a cached or deterministic result was used.</span>
      </div>
    );
  }
  if (!usage.tracking_complete || usage.unpriced_calls > 0) {
    return (
      <div className="ai-action-cost warning">
        <strong>Cost record incomplete</strong>
        <span>The action completed, but one or more API usage records were unavailable.</span>
      </div>
    );
  }
  return (
    <div className="ai-action-cost">
      <strong>{usd(usage.calculated_cost_usd)} calculated</strong>
      <span>
        {usage.api_calls} call{usage.api_calls === 1 ? "" : "s"} / {tokenCount(usage.total_tokens)} tokens
        {usage.web_search_calls ? ` / ${usage.web_search_calls} web search${usage.web_search_calls === 1 ? "" : "es"}` : ""}
      </span>
    </div>
  );
}

function AIUsageCard({ report }: { report: AIUsageReport | null }) {
  if (!report) return null;
  return (
    <section className="ai-usage-card">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Measured API usage</p>
          <h3>AI cost control</h3>
          <p>Luna is used only for official-JD intelligence and resume/cover-letter planning.</p>
        </div>
        <span className="safe-badge">Calculated / not invoice</span>
      </div>
      <div className="ai-usage-metrics">
        <div><small>Today</small><strong>{usd(report.today.calculated_cost_usd)}</strong><span>{report.today.api_calls} calls</span></div>
        <div><small>This month</small><strong>{usd(report.current_month.calculated_cost_usd)}</strong><span>{tokenCount(report.current_month.total_tokens)} tokens</span></div>
        <div><small>All recorded</small><strong>{usd(report.all_time.calculated_cost_usd)}</strong><span>{report.all_time.api_calls} calls since tracking began</span></div>
        <div><small>Cached input</small><strong>{tokenCount(report.current_month.cached_input_tokens)}</strong><span>tokens billed at cache rate</span></div>
        <div><small>Web search</small><strong>{report.current_month.web_search_calls}</strong><span>{usd(report.current_month.web_search_calls * report.pricing.web_search_per_call_usd)} tool fees</span></div>
      </div>
      <details className="ai-usage-details">
        <summary>Recent AI calls and pricing details</summary>
        {report.recent_events.length ? (
          <div className="ai-usage-events">
            {report.recent_events.slice(0, 8).map((event) => (
              <div key={event.event_id}>
                <span><strong>{event.operation_label}</strong>{event.company ? ` / ${event.company}` : ""}</span>
                <span>{tokenCount(event.total_tokens)} tokens{event.web_search_calls ? ` / ${event.web_search_calls} search` : ""}</span>
                <strong>{usd(event.calculated_cost_usd)}</strong>
              </div>
            ))}
          </div>
        ) : <p>No measured AI calls yet.</p>}
        <p>
          Prices use snapshot {report.pricing.version}. The OpenAI billing dashboard remains
          authoritative. Usage metadata is mirrored to {report.storage.drive_path}; prompts,
          documents, email content, and credentials are excluded. Calls made before this
          feature was enabled are not reconstructed.
        </p>
      </details>
    </section>
  );
}

function SkillList({
  values,
  empty,
  evidence = {},
}: {
  values: string[];
  empty: string;
  evidence?: Record<string, string>;
}) {
  if (!values.length) return <span className="muted">{empty}</span>;
  return (
    <div className="skill-list">
      {values.map((value) => (
        <span key={value} title={evidence[value] || undefined}>{value}</span>
      ))}
    </div>
  );
}

function CandidateCard({
  candidate,
  selected,
  onSelect,
  evidenceDrafts,
  onEvidenceChange,
}: {
  candidate: OfficialJobCandidate;
  selected: boolean;
  onSelect: () => void;
  evidenceDrafts: Record<string, EvidenceDraft>;
  onEvidenceChange: (skill: string, value: EvidenceDraft) => void;
}) {
  const missingSkills = candidate.eligibility.missing_skills ?? [];
  const equivalentMatches = candidate.eligibility.equivalent_matched_skills ?? [];
  const exactMatches = candidate.eligibility.exact_matched_skills
    ?? candidate.eligibility.matched_skills.filter((skill) => !equivalentMatches.includes(skill));
  return (
    <article className={`official-candidate ${selected ? "selected" : ""}`}>
      <label className="candidate-choice">
        <input type="radio" checked={selected} onChange={onSelect} />
        <span>
          <strong>{candidate.title}</strong>
          <small>{[candidate.company, candidate.location].filter(Boolean).join(" / ")}</small>
        </span>
      </label>
      <div className="candidate-links">
        <a href={candidate.official_url} target="_blank" rel="noreferrer">Open official job</a>
        <span className={`value-chip ${candidate.active_status}`}>{candidate.active_status || "unknown"}</span>
      </div>

      <div className="score-pair">
        <div>
          <small>Alert to official identity</small>
          <strong>{candidate.official_match_score}/100</strong>
          <p>{candidate.official_match_reason || "Identity evidence is limited."}</p>
        </div>
        <div>
          <small>Resume eligibility</small>
          <strong>{candidate.eligibility.score}/100 / {candidate.eligibility.band}</strong>
          <p>{candidate.eligibility.experience_reason}</p>
        </div>
      </div>

      <details className="candidate-details" open={selected}>
        <summary>JD evidence and eligibility details</summary>
        <p className="jd-summary">{candidate.description_summary || "No reliable description summary was returned."}</p>
        <dl>
          <div><dt>Published</dt><dd>{candidate.published_at || "Not supplied"}</dd></div>
          <div><dt>Requisition</dt><dd>{candidate.requisition_id || "Not supplied"}</dd></div>
          <div><dt>Experience</dt><dd>{candidate.experience_text || "Not stated"}</dd></div>
          <div><dt>Work type</dt><dd>{candidate.workplace_type || candidate.employment_type || "Not stated"}</dd></div>
        </dl>
        <h4>Required skills</h4>
        <SkillList
          values={candidate.required_skills}
          evidence={candidate.required_skill_evidence}
          empty="Not reliably extracted"
        />
        {Object.keys(candidate.required_skill_evidence ?? {}).length > 0 && (
          <details className="skill-evidence">
            <summary>Show exact JD evidence</summary>
            <ul>
              {candidate.required_skills.map((skill) => (
                <li key={skill}>
                  <strong>{skill}:</strong> {candidate.required_skill_evidence?.[skill]}
                </li>
              ))}
            </ul>
          </details>
        )}
        <h4>Exact wording already in your resume</h4>
        <SkillList values={exactMatches} empty="No exact JD wording is present yet" />
        {equivalentMatches.length > 0 && (
          <div className="equivalent-match-block">
            <h4>Equivalent documented evidence</h4>
            <SkillList values={equivalentMatches} empty="" />
            <p>
              The capability is already supported by similar resume wording. Generation can
              add the employer&apos;s exact phrase naturally; it is not counted as an exact ATS
              keyword until it appears in the tailored DOCX.
            </p>
          </div>
        )}
        <h4>Still unsupported after exact/equivalent comparison</h4>
        {candidate.eligibility.gaps.length ? (
          <ul>{candidate.eligibility.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
        ) : <p className="muted">No explicit gap was found from the available requirements.</p>}
        {missingSkills.length > 0 && (
          <section className="gap-evidence-section">
            <div>
              <h4>Add evidence only for skills you actually used</h4>
              <p>
                The active baseline is checked first for equivalent wording. For a remaining
                gap, explain what you did; a confirmed keyword is placed under the most
                relevant Technical Skills heading. Unconfirmed gaps stay excluded.
              </p>
            </div>
            <div className="gap-evidence-grid">
              {missingSkills.map((skill) => {
                const draft = evidenceDrafts[skillKey(skill)] ?? {
                  skill,
                  note: "",
                  confirmed: false,
                };
                const noteReady = draft.note.trim().length >= 20;
                return (
                  <article className={`gap-evidence-card ${draft.confirmed ? "confirmed" : ""}`} key={skill}>
                    <div className="gap-evidence-heading">
                      <strong>{skill}</strong>
                      <span>{draft.confirmed ? "Ready for Skills" : "Not included"}</span>
                    </div>
                    <label>
                      Your factual evidence note
                      <textarea
                        rows={3}
                        maxLength={1200}
                        value={draft.note}
                        placeholder="Example: Built and evaluated an agent workflow for a personal or work project; describe only what you actually did."
                        onChange={(event) => onEvidenceChange(skill, {
                          ...draft,
                          skill,
                          note: event.target.value,
                          confirmed: draft.confirmed && event.target.value.trim().length >= 20,
                        })}
                      />
                    </label>
                    <label className="evidence-confirmation">
                      <input
                        type="checkbox"
                        checked={draft.confirmed}
                        disabled={!noteReady}
                        onChange={(event) => onEvidenceChange(skill, {
                          ...draft,
                          skill,
                          confirmed: event.target.checked,
                        })}
                      />
                      <span>I confirm this is accurate and may be used in my tailored resume.</span>
                    </label>
                    {!noteReady && draft.note.length > 0 && (
                      <small>Add at least 20 characters of factual context before confirming.</small>
                    )}
                  </article>
                );
              })}
            </div>
            <p className="evidence-storage-note">
              Confirmed notes are sent to Luna only when you generate documents and are stored privately in the Drive resume library.
            </p>
          </section>
        )}
        <p className="score-components">{candidate.eligibility.components}</p>
        {candidate.source_notes && <p className="source-evidence-note">{candidate.source_notes}</p>}
      </details>
    </article>
  );
}

function ArtifactCard({ artifact }: { artifact: GeneratedArtifact }) {
  return (
    <article className="artifact-card">
      <div>
        <strong>{OUTPUT_LABELS[artifact.kind]}</strong>
        <span>{artifact.file_name}</span>
      </div>
      <div className="action-row compact-actions">
        <a className="primary-button" href={artifact.download_url}>Download</a>
        <a className="secondary-button" href={artifact.drive_url} target="_blank" rel="noreferrer">Open in Drive</a>
      </div>
    </article>
  );
}

function AtsAlignmentCard({
  comparison,
}: {
  comparison: GeneratedDocumentSet["ats_alignment"];
}) {
  const beforeScore = comparison.before.score;
  const afterScore = comparison.after?.score ?? null;
  const delta = comparison.delta;
  const beforeMatches = new Set([
    ...comparison.before.matched_required,
    ...comparison.before.matched_preferred,
  ].map(skillKey));
  const newlyCovered = comparison.after
    ? [
      ...comparison.after.matched_required,
      ...comparison.after.matched_preferred,
    ].filter((value) => !beforeMatches.has(skillKey(value)))
    : [];
  const scoreLabel = (value: number | null) => value === null ? "N/A" : `${value}/100`;
  const changeLabel = delta === null
    ? "No tailored resume was generated"
    : delta > 0
      ? "New supported terms covered"
      : delta < 0
        ? "Review reduced keyword coverage"
        : "Keyword coverage unchanged";

  return (
    <section className="ats-alignment-card" aria-labelledby="ats-alignment-heading">
      <div className="ats-alignment-heading">
        <div>
          <h4 id="ats-alignment-heading">ATS keyword alignment estimate</h4>
          <p>Verified JD terms measured against the selected baseline and generated copy.</p>
        </div>
        <span>Local / deterministic</span>
      </div>
      <div className="ats-score-grid">
        <div>
          <small>Before / baseline</small>
          <strong>{scoreLabel(beforeScore)}</strong>
          <span>{comparison.before.band}</span>
        </div>
        <div className="after">
          <small>After / tailored copy</small>
          <strong>{scoreLabel(afterScore)}</strong>
          <span>{comparison.after?.band ?? "Generate a resume DOCX or PDF"}</span>
        </div>
        <div className={delta !== null && delta > 0 ? "improved" : ""}>
          <small>Change</small>
          <strong>{delta === null ? "N/A" : `${delta > 0 ? "+" : ""}${delta}`}</strong>
          <span>{changeLabel}</span>
        </div>
      </div>
      {newlyCovered.length > 0 && (
        <div className="newly-covered-terms">
          <strong>Newly covered in the tailored copy</strong>
          <SkillList values={newlyCovered} empty="" />
        </div>
      )}
      <details className="ats-methodology">
        <summary>How this estimate is calculated</summary>
        <p>{comparison.methodology}</p>
        <p><strong>Before:</strong> {comparison.before.breakdown}</p>
        {comparison.after && <p><strong>After:</strong> {comparison.after.breakdown}</p>}
      </details>
    </section>
  );
}

export default function JobIntelligencePanel({
  job,
  googleConnected,
  onClose,
  onOfficialUrl,
}: {
  job: JobRow;
  googleConnected: boolean;
  onClose: () => void;
  onOfficialUrl?: (url: string) => void;
}) {
  const [status, setStatus] = useState<JobIntelligenceStatus | null>(null);
  const [usageReport, setUsageReport] = useState<AIUsageReport | null>(null);
  const [analysis, setAnalysis] = useState<JobAnalysis | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [generation, setGeneration] = useState<GeneratedDocumentSet | null>(null);
  const [evidenceDrafts, setEvidenceDrafts] = useState<Record<string, EvidenceDraft>>({});
  const [outputs, setOutputs] = useState<GeneratedArtifactKind[]>(["resume_docx"]);
  const [busy, setBusy] = useState<"status" | "analysis" | "baseline" | "references" | "documents" | "">("status");
  const [message, setMessage] = useState<{ kind: "error" | "info" | "success"; text: string } | null>(null);
  const baselineRef = useRef<HTMLInputElement>(null);
  const referencesRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    api.jobIntelligenceStatus()
      .then((value) => {
        if (active) {
          setStatus(value);
          setUsageReport(value.ai_usage ?? null);
          const saved = Object.fromEntries(
            (value.confirmed_skill_evidence ?? []).map((entry) => [
              skillKey(entry.skill),
              { ...entry, confirmed: true },
            ]),
          );
          setEvidenceDrafts((current) => ({ ...saved, ...current }));
        }
      })
      .catch((error: Error) => {
        if (active) setMessage({ kind: "error", text: error.message });
      })
      .finally(() => {
        if (active) setBusy("");
      });
    return () => { active = false; };
  }, []);

  const selected = useMemo(
    () => analysis?.candidates.find((candidate) => candidate.official_job_id === selectedId) ?? null,
    [analysis, selectedId],
  );
  const driveReady = Boolean(googleConnected && status?.drive_connected);

  const refreshUsage = async () => {
    try {
      setUsageReport(await api.aiUsage());
    } catch {
      // Per-action usage still remains visible in the action response.
    }
  };

  const updateEvidence = (skill: string, value: EvidenceDraft) => {
    setEvidenceDrafts((current) => ({
      ...current,
      [skillKey(skill)]: value,
    }));
    setGeneration(null);
  };

  const confirmedEvidence = useMemo(() => {
    if (!selected) return [];
    return (selected.eligibility.missing_skills ?? [])
      .map((skill) => evidenceDrafts[skillKey(skill)])
      .filter((entry): entry is EvidenceDraft => Boolean(
        entry?.confirmed && entry.note.trim().length >= 20,
      ))
      .map((entry) => ({
        skill: entry.skill,
        note: entry.note.trim(),
        confirmed: true,
      }));
  }, [evidenceDrafts, selected]);

  const runAnalysis = async (refresh = false) => {
    if (!status?.openai_configured) {
      setMessage({ kind: "error", text: "Configure OPENAI_API_KEY on the FastAPI server first." });
      return;
    }
    if (refresh && !window.confirm("Refresh ignores the saved result and creates a new Luna verification/extraction call. Continue?")) return;
    setBusy("analysis");
    setGeneration(null);
    setMessage({ kind: "info", text: refresh ? "Refreshing the official source..." : "Checking the private cache, then the official public source if needed..." });
    try {
      const response = await api.analyzeJob(job, refresh);
      setAnalysis(response.analysis);
      const first = response.analysis.candidates[0];
      setSelectedId(first?.official_job_id ?? "");
      if (first?.official_url) onOfficialUrl?.(first.official_url);
      setMessage({
        kind: response.analysis.candidates.length
          ? "success"
          : response.analysis.warnings?.length
            ? "error"
            : "info",
        text: response.analysis.candidates.length
          ? `${response.analysis.candidates.length} official candidate(s) found${response.analysis.cached ? " from cache" : " with Luna"}.`
          : response.analysis.warnings?.[0]
            ?? "No current public official posting could be verified. No documents were generated.",
      });
      await refreshUsage();
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      setBusy("");
    }
  };

  const chooseCandidate = (candidate: OfficialJobCandidate) => {
    setSelectedId(candidate.official_job_id);
    setGeneration(null);
    onOfficialUrl?.(candidate.official_url);
  };

  const uploadBaseline = async (file: File | undefined) => {
    if (!file) return;
    if (!driveReady) {
      setMessage({ kind: "error", text: "Reconnect Google before changing the Drive baseline." });
      return;
    }
    setBusy("baseline");
    setMessage({ kind: "info", text: "Validating and storing a new immutable baseline version in Drive..." });
    try {
      const nextStatus = await api.uploadBaselineResume(file);
      setStatus(nextStatus);
      setGeneration(null);
      setMessage({ kind: "success", text: "The new Drive baseline is active. Earlier baseline versions remain unchanged." });
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      if (baselineRef.current) baselineRef.current.value = "";
      setBusy("");
    }
  };

  const uploadReferences = async (files: FileList | null) => {
    const selectedFiles = files ? Array.from(files) : [];
    if (!selectedFiles.length) return;
    if (!driveReady) {
      setMessage({ kind: "error", text: "Reconnect Google before adding Drive reference files." });
      return;
    }
    setBusy("references");
    setMessage({ kind: "info", text: `Validating and storing ${selectedFiles.length} reference file(s) in Drive...` });
    try {
      const nextStatus = await api.uploadReferenceDocuments(selectedFiles);
      setStatus(nextStatus);
      setGeneration(null);
      setMessage({ kind: "success", text: `${selectedFiles.length} reference file(s) are available for truthful evidence matching.` });
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      if (referencesRef.current) referencesRef.current.value = "";
      setBusy("");
    }
  };

  const toggleOutput = (kind: GeneratedArtifactKind) => {
    setOutputs((current) => current.includes(kind)
      ? current.filter((value) => value !== kind)
      : [...current, kind]);
    setGeneration(null);
  };

  const generateDocuments = async () => {
    if (!analysis || !selected) return;
    if (!status?.baseline_resume_configured) {
      setMessage({ kind: "error", text: "Add a baseline DOCX to the Drive library before generating documents." });
      return;
    }
    if (!driveReady) {
      setMessage({ kind: "error", text: "Reconnect Google before generating Drive documents." });
      return;
    }
    if (!outputs.length) {
      setMessage({ kind: "error", text: "Select at least one output: DOCX, PDF, or cover letter." });
      return;
    }
    setBusy("documents");
    setGeneration(null);
    setMessage({ kind: "info", text: "Creating, validating, and uploading the selected documents to Drive..." });
    try {
      const response = await api.generateDocuments({
        analysisId: analysis.analysis_id,
        officialJobId: selected.official_job_id,
        outputs,
        confirmedSkillEvidence: confirmedEvidence,
      });
      setGeneration(response.generation);
      const folderPath = response.generation.artifacts[0]?.folder_path;
      setMessage({
        kind: "success",
        text: `${response.generation.artifacts.length} document(s) created in ${folderPath || "the Drive application folder"}.`,
      });
      await refreshUsage();
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.currentTarget === event.target && !busy) onClose();
    }}>
      <section className="intelligence-panel" role="dialog" aria-modal="true" aria-labelledby="intelligence-title">
        <header>
          <div>
            <p className="eyebrow">Manual / per job</p>
            <h2 id="intelligence-title">Official JD, eligibility and documents</h2>
            <p>{text(job.title)} / {text(job.company)}{text(job.location) ? ` / ${text(job.location)}` : ""}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} disabled={Boolean(busy)} aria-label="Close job tool">x</button>
        </header>

        <div className="intelligence-body">
          {message && <div className={`inline-message ${message.kind}`}>{message.text}</div>}

          <section className="privacy-strip">
            <span>{status?.openai_configured ? `Luna ready / ${status.model}` : "OpenAI key not configured"}</span>
            <span>{driveReady ? "Google Drive connected" : "Google Drive connection required"}</span>
            <span>No Gmail body, contacts, or connection data sent</span>
          </section>

          <AIUsageCard report={usageReport} />

          <section className="manual-action-card library-card">
            <div className="section-heading-row">
              <div>
                <h3>Drive resume library</h3>
                <p>The active baseline is immutable. Uploading another resume creates a new version instead of changing the original.</p>
              </div>
              {status?.library_url && <a className="secondary-button" href={status.library_url} target="_blank" rel="noreferrer">Open library</a>}
            </div>

            <div className="library-status-grid">
              <div className="library-status-item">
                <small>Active baseline</small>
                <strong>{status?.baseline_resume_name || "Not configured"}</strong>
                {status?.baseline_uploaded_at && <span>Stored {status.baseline_uploaded_at}</span>}
                {status?.baseline_drive_url && <a href={status.baseline_drive_url} target="_blank" rel="noreferrer">Open baseline in Drive</a>}
              </div>
              <div className="library-status-item">
                <small>Reference documents</small>
                <strong>{status?.reference_document_count ?? 0} available</strong>
                <span>Only supported, contact-free evidence is considered during planning.</span>
              </div>
            </div>

            {status?.message && <p className="resume-warning">{status.message}</p>}

            <div className="library-actions">
              <label className={`secondary-button file-action-label ${!driveReady || Boolean(busy) ? "disabled" : ""}`}>
                Add new baseline DOCX
                <input
                  ref={baselineRef}
                  className="visually-hidden"
                  type="file"
                  accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(event) => uploadBaseline(event.target.files?.[0])}
                  disabled={!driveReady || Boolean(busy)}
                />
              </label>
              <label className={`secondary-button file-action-label ${!driveReady || Boolean(busy) ? "disabled" : ""}`}>
                Add reference files
                <input
                  ref={referencesRef}
                  className="visually-hidden"
                  type="file"
                  multiple
                  accept=".docx,.md,.txt,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown,text/plain"
                  onChange={(event) => uploadReferences(event.target.files)}
                  disabled={!driveReady || Boolean(busy)}
                />
              </label>
            </div>

            {Boolean(status?.reference_documents?.length) && (
              <ul className="reference-list">
                {status?.reference_documents?.map((reference) => (
                  <li key={reference.sha256}>
                    <a href={reference.drive_url} target="_blank" rel="noreferrer">{reference.original_name}</a>
                    <span>{reference.uploaded_at || "Stored in Drive"}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="manual-action-card">
            <div>
              <h3>1. Find the official posting and score eligibility</h3>
              <p>This checks the private cache first. A new or refreshed supported ATS job uses its exact public JD; other jobs use exact-only Luna web research when an official URL is already known.</p>
            </div>
            <CostEstimate
              estimate={usageReport?.estimates.official_job}
              area="Exact ATS extraction uses tokens only; broader official-job research may also use paid web search"
            />
            <div className="action-row">
              <button className="primary-button" type="button" disabled={Boolean(busy) || !status?.openai_configured} onClick={() => runAnalysis(false)}>
                {busy === "analysis" ? "Analyzing..." : analysis ? "Load / reuse analysis" : "Find official JD + score"}
              </button>
              {analysis && <button className="secondary-button" type="button" disabled={Boolean(busy)} onClick={() => runAnalysis(true)}>Refresh with Luna</button>}
            </div>
            {analysis && <ActionCost usage={analysis.ai_usage} />}
          </section>

          {analysis && (
            <section className="candidate-section">
              <div className="section-heading-row">
                <div>
                  <h3>Official candidates</h3>
                  <p>
                    Identity and eligibility remain separate. Eligibility uses the active
                    baseline resume when available and recognizes cautious equivalent wording.
                  </p>
                </div>
                <span className="safe-badge">{analysis.cached ? "Cache reused / no new research call" : `Researched ${analysis.verified_at}`}</span>
              </div>
              {analysis.candidates.length ? analysis.candidates.map((candidate) => (
                <CandidateCard
                  key={candidate.official_job_id}
                  candidate={candidate}
                  selected={candidate.official_job_id === selectedId}
                  onSelect={() => chooseCandidate(candidate)}
                  evidenceDrafts={evidenceDrafts}
                  onEvidenceChange={updateEvidence}
                />
              )) : <div className="empty-inline">No verified official candidate is available for this alert.</div>}
            </section>
          )}

          <section className="manual-action-card resume-action-card">
            <div>
              <h3>2. Choose and generate application documents</h3>
              <p>The model may naturally reframe supported summary and experience wording, while exact JD terms are placed in relevant skill categories. It cannot alter the baseline, invent achievements, change metrics, or submit an application.</p>
            </div>
            <div className="output-options" role="group" aria-label="Generated document formats">
              {(Object.keys(OUTPUT_LABELS) as GeneratedArtifactKind[]).map((kind) => (
                <label className="toggle-row output-option" key={kind}>
                  <input
                    type="checkbox"
                    checked={outputs.includes(kind)}
                    disabled={Boolean(busy)}
                    onChange={() => toggleOutput(kind)}
                  />
                  <span>{OUTPUT_LABELS[kind]}</span>
                </label>
              ))}
            </div>
            <div className={`confirmed-evidence-summary ${confirmedEvidence.length ? "ready" : ""}`}>
              <strong>{confirmedEvidence.length} confirmed JD keyword{confirmedEvidence.length === 1 ? "" : "s"}</strong>
              <span>
                {confirmedEvidence.length
                  ? "These exact terms will be added to Technical Skills in the generated copy."
                  : "No gap keywords will be added unless you provide evidence and confirm it."}
              </span>
            </div>
            <p className="drive-destination">
              Selected files use neutral names and are uploaded to <strong>Job Hunt / Resumes / Company / YYYY-MM-DD_Role</strong>.
            </p>
            <CostEstimate
              estimate={usageReport?.estimates.resume_plan}
              area="One Luna plan covers the selected resume formats and optional cover letter; DOCX/PDF creation is local"
            />
            <button
              className="primary-button"
              type="button"
              disabled={Boolean(busy) || !selected || !status?.baseline_resume_configured || !driveReady || !outputs.length}
              onClick={generateDocuments}
            >
              {busy === "documents" ? "Generating and verifying..." : `Generate ${outputs.length || 0} selected document${outputs.length === 1 ? "" : "s"}`}
            </button>
          </section>

          {generation && (
            <section className="resume-result">
              <div className="section-heading-row">
                <div>
                  <h3>Application documents ready</h3>
                  <p>{generation.artifacts.length} verified file(s) / generated {generation.generated_at}</p>
                  {generation.artifacts[0]?.folder_path && <p>{generation.artifacts[0].folder_path}</p>}
                </div>
                {generation.artifacts[0]?.folder_url && <a className="secondary-button" href={generation.artifacts[0].folder_url} target="_blank" rel="noreferrer">Open Drive folder</a>}
              </div>
              <ActionCost usage={generation.ai_usage} />
              <div className="artifact-grid">
                {generation.artifacts.map((artifact) => <ArtifactCard artifact={artifact} key={artifact.artifact_id} />)}
              </div>
              {generation.ats_alignment && <AtsAlignmentCard comparison={generation.ats_alignment} />}
              {generation.reference_points_used.length > 0 && <><h4>Reference evidence used</h4><ul>{generation.reference_points_used.map((point) => <li key={point}>{point}</li>)}</ul></>}
              {(generation.documented_equivalent_skills_added ?? []).length > 0 && <><h4>Equivalent evidence translated to exact JD wording</h4><SkillList values={generation.documented_equivalent_skills_added} empty="" /></>}
              {generation.confirmed_skills_added.length > 0 && <><h4>User-confirmed skills added</h4><SkillList values={generation.confirmed_skills_added} empty="" /></>}
              {(generation.skill_placements ?? []).length > 0 && (
                <details className="skill-placement-details">
                  <summary>Where JD keywords were placed</summary>
                  <ul>{generation.skill_placements.map((item) => <li key={item.skill}><strong>{item.skill}</strong> / {item.category}</li>)}</ul>
                </details>
              )}
              {(generation.experience_bullets_reframed ?? 0) > 0 && <p className="source-evidence-note">{generation.experience_bullets_reframed} existing experience bullet(s) were naturally reframed after validation; facts and metrics were preserved.</p>}
              {generation.keyword_alignment.length > 0 && <><h4>Supported keywords emphasized</h4><SkillList values={generation.keyword_alignment} empty="" /></>}
              {generation.change_notes.length > 0 && <><h4>What changed</h4><ul>{generation.change_notes.map((note) => <li key={note}>{note}</li>)}</ul></>}
              {generation.warnings.map((warning) => <p className="resume-warning" key={warning}>{warning}</p>)}
              <p className="review-warning"><strong>Review required:</strong> these are application drafts and were not submitted anywhere.</p>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}
