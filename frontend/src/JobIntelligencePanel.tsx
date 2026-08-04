import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type {
  GeneratedResume,
  JobAnalysis,
  JobIntelligenceStatus,
  JobRow,
  OfficialJobCandidate,
  Scalar,
} from "./types";

function text(value: Scalar | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function SkillList({ values, empty }: { values: string[]; empty: string }) {
  if (!values.length) return <span className="muted">{empty}</span>;
  return <div className="skill-list">{values.map((value) => <span key={value}>{value}</span>)}</div>;
}

function CandidateCard({
  candidate,
  selected,
  onSelect,
}: {
  candidate: OfficialJobCandidate;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <article className={`official-candidate ${selected ? "selected" : ""}`}>
      <label className="candidate-choice">
        <input type="radio" checked={selected} onChange={onSelect} />
        <span>
          <strong>{candidate.title}</strong>
          <small>{[candidate.company, candidate.location].filter(Boolean).join(" · ")}</small>
        </span>
      </label>
      <div className="candidate-links">
        <a href={candidate.official_url} target="_blank" rel="noreferrer">Open official job ↗</a>
        <span className={`value-chip ${candidate.active_status}`}>{candidate.active_status || "unknown"}</span>
      </div>

      <div className="score-pair">
        <div>
          <small>Alert → official identity</small>
          <strong>{candidate.official_match_score}/100</strong>
          <p>{candidate.official_match_reason || "Identity evidence is limited."}</p>
        </div>
        <div>
          <small>Resume eligibility</small>
          <strong>{candidate.eligibility.score}/100 · {candidate.eligibility.band}</strong>
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
        <SkillList values={candidate.required_skills} empty="Not reliably extracted" />
        <h4>Your documented matches</h4>
        <SkillList values={candidate.eligibility.matched_skills} empty="No exact skill labels matched" />
        <h4>Gaps to review honestly</h4>
        {candidate.eligibility.gaps.length ? (
          <ul>{candidate.eligibility.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
        ) : <p className="muted">No explicit gap was found from the available requirements.</p>}
        <p className="score-components">{candidate.eligibility.components}</p>
      </details>
    </article>
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
  const [analysis, setAnalysis] = useState<JobAnalysis | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [resume, setResume] = useState<GeneratedResume | null>(null);
  const [uploadToDrive, setUploadToDrive] = useState(googleConnected);
  const [busy, setBusy] = useState<"status" | "analysis" | "upload" | "resume" | "">("status");
  const [message, setMessage] = useState<{ kind: "error" | "info" | "success"; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    api.jobIntelligenceStatus()
      .then((value) => {
        if (active) setStatus(value);
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

  const runAnalysis = async (refresh = false) => {
    if (!status?.openai_configured) {
      setMessage({ kind: "error", text: "Configure OPENAI_API_KEY on the FastAPI server first." });
      return;
    }
    if (refresh && !window.confirm("Refresh ignores the saved result and creates a new Luna web-research call. Continue?")) return;
    setBusy("analysis");
    setResume(null);
    setMessage({ kind: "info", text: refresh ? "Refreshing the official source…" : "Checking the private cache, then the official public source if needed…" });
    try {
      const response = await api.analyzeJob(job, refresh);
      setAnalysis(response.analysis);
      const first = response.analysis.candidates[0];
      setSelectedId(first?.official_job_id ?? "");
      if (first?.official_url) onOfficialUrl?.(first.official_url);
      setMessage({
        kind: response.analysis.candidates.length ? "success" : "info",
        text: response.analysis.candidates.length
          ? `${response.analysis.candidates.length} official candidate(s) found${response.analysis.cached ? " from cache" : " with Luna"}.`
          : "No current public official posting could be verified. No resume was generated.",
      });
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      setBusy("");
    }
  };

  const chooseCandidate = (candidate: OfficialJobCandidate) => {
    setSelectedId(candidate.official_job_id);
    setResume(null);
    onOfficialUrl?.(candidate.official_url);
  };

  const uploadBaseline = async (file: File | undefined) => {
    if (!file) return;
    setBusy("upload");
    setMessage({ kind: "info", text: "Validating and storing the baseline DOCX privately…" });
    try {
      const nextStatus = await api.uploadBaselineResume(file);
      setStatus(nextStatus);
      setMessage({ kind: "success", text: "Baseline resume saved privately. Contact details remain outside OpenAI." });
    } catch (error) {
      setMessage({ kind: "error", text: (error as Error).message });
    } finally {
      if (fileRef.current) fileRef.current.value = "";
      setBusy("");
    }
  };

  const generateResume = async () => {
    if (!analysis || !selected) return;
    if (!status?.baseline_resume_configured) {
      setMessage({ kind: "error", text: "Upload a baseline DOCX before generating a tailored copy." });
      return;
    }
    setBusy("resume");
    setResume(null);
    setMessage({ kind: "info", text: "Creating a truth-preserving resume plan and verifying the DOCX…" });
    try {
      const response = await api.generateResume({
        analysisId: analysis.analysis_id,
        officialJobId: selected.official_job_id,
        uploadToDrive,
      });
      setResume(response.resume);
      setMessage({ kind: "success", text: "Tailored draft created. Review it before applying." });
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
            <p className="eyebrow">Manual · per job</p>
            <h2 id="intelligence-title">Official JD, eligibility & resume</h2>
            <p>{text(job.title)} · {text(job.company)}{text(job.location) ? ` · ${text(job.location)}` : ""}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} disabled={Boolean(busy)} aria-label="Close job tool">×</button>
        </header>

        <div className="intelligence-body">
          {message && <div className={`inline-message ${message.kind}`}>{message.text}</div>}

          <section className="privacy-strip">
            <span>{status?.openai_configured ? `Luna ready · ${status.model}` : "OpenAI key not configured"}</span>
            <span>{status?.baseline_resume_configured ? `Baseline ready · ${status.baseline_resume_name}` : "Baseline resume needed"}</span>
            <span>No Gmail body, contacts, or connection data sent</span>
          </section>

          <section className="manual-action-card">
            <div>
              <h3>1. Find the official posting and score eligibility</h3>
              <p>This button checks the private cache first. Only a new or explicitly refreshed job creates a Luna web-research call.</p>
            </div>
            <div className="action-row">
              <button className="primary-button" type="button" disabled={Boolean(busy) || !status?.openai_configured} onClick={() => runAnalysis(false)}>
                {busy === "analysis" ? "Analyzing…" : analysis ? "Load / reuse analysis" : "Find official JD + score"}
              </button>
              {analysis && <button className="secondary-button" type="button" disabled={Boolean(busy)} onClick={() => runAnalysis(true)}>Refresh with Luna</button>}
            </div>
          </section>

          {analysis && (
            <section className="candidate-section">
              <div className="section-heading-row">
                <div>
                  <h3>Official candidates</h3>
                  <p>Identity score and resume eligibility are intentionally separate.</p>
                </div>
                <span className="safe-badge">{analysis.cached ? "Cache reused · no new research call" : `Researched ${analysis.verified_at}`}</span>
              </div>
              {analysis.candidates.length ? analysis.candidates.map((candidate) => (
                <CandidateCard
                  key={candidate.official_job_id}
                  candidate={candidate}
                  selected={candidate.official_job_id === selectedId}
                  onSelect={() => chooseCandidate(candidate)}
                />
              )) : <div className="empty-inline">No verified official candidate is available for this alert.</div>}
            </section>
          )}

          <section className="manual-action-card resume-action-card">
            <div>
              <h3>2. Generate a tailored DOCX draft</h3>
              <p>The model writes a supported summary and ranks existing evidence. It cannot add or rewrite achievements, employers, dates, or metrics.</p>
            </div>
            <div className="baseline-controls">
              <input
                ref={fileRef}
                type="file"
                accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={(event) => uploadBaseline(event.target.files?.[0])}
                disabled={Boolean(busy)}
              />
              <label className="toggle-row compact">
                <input type="checkbox" checked={uploadToDrive} disabled={!googleConnected || Boolean(busy)} onChange={(event) => setUploadToDrive(event.target.checked)} />
                <span>Upload generated draft to Job Hunt / date / Resumes</span>
              </label>
            </div>
            <button className="primary-button" type="button" disabled={Boolean(busy) || !selected || !status?.baseline_resume_configured} onClick={generateResume}>
              {busy === "resume" ? "Generating and verifying…" : "Generate tailored DOCX"}
            </button>
          </section>

          {resume && (
            <section className="resume-result">
              <div>
                <h3>Draft ready</h3>
                <p>{resume.file_name}</p>
              </div>
              <div className="action-row">
                <a className="primary-button" href={resume.download_url}>Download DOCX</a>
                {resume.drive_url && <a className="secondary-button" href={resume.drive_url} target="_blank" rel="noreferrer">Open in Drive ↗</a>}
              </div>
              {resume.keyword_alignment.length > 0 && <><h4>Supported keywords emphasized</h4><SkillList values={resume.keyword_alignment} empty="" /></>}
              {resume.change_notes.length > 0 && <><h4>What changed</h4><ul>{resume.change_notes.map((note) => <li key={note}>{note}</li>)}</ul></>}
              {resume.warnings.map((warning) => <p className="resume-warning" key={warning}>{warning}</p>)}
              <p className="review-warning"><strong>Review required:</strong> this is an application draft, not an automatically submitted resume.</p>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}
