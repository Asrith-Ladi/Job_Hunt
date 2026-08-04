import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { NetworkConnectionRow, NetworkConnectionsResponse } from "./types";

type Notice = { kind: "success" | "error" | "info"; text: string };
type OutreachRecord = { status: string; last_contacted: string; notes: string };
type OutreachState = Record<string, OutreachRecord>;
type NetworkColumnKey =
  | "name"
  | "position"
  | "current_company"
  | "connected_on"
  | "category"
  | "message_action"
  | "outreach_status"
  | "last_contacted"
  | "notes"
  | "relevance_reason"
  | "relevance_score"
  | "registry_company"
  | "registry_category"
  | "referral_status"
  | "match_method"
  | "official_careers_page"
  | "direct_job_portal"
  | "email_address";

const DEFAULT_TARGET_ROLES = "AI Engineer, ML Engineer, and Generative AI Engineer";
const PAGE_SIZE = 50;
const GREETING_STORAGE_KEY = "job_hunt.network.greeting_template";
const BODY_STORAGE_KEY = "job_hunt.network.message_body";
const OUTREACH_STORAGE_KEY = "job_hunt.network.outreach_state";

const LEGACY_SINGLE_LINE_GREETING =
  "Hi {first_name}, hope you're doing well. Glad to connect with you. " +
  "I noticed you're working as {position} at {company}.";

const DEFAULT_GREETING = `Hi {first_name},

Hope you're doing well.

Glad to connect with you.

I noticed you're working as {position} at {company}.`;

const DEFAULT_BODY = `I'm currently preparing for AI Engineer / ML Engineer / Generative AI Engineer opportunities and trying to understand where I currently stand compared with industry expectations.

Since you're working in this area, I wanted to ask whether you would be comfortable reviewing my resume and sharing a few honest suggestions. I'm mainly looking for feedback on:

• How my profile is positioned for AI/ML roles
• Technical areas or projects I should strengthen
• Any improvements needed in my job-search approach

Even two or three points from your experience would be very helpful. I can share my resume here if that's okay with you.`;

const NETWORK_COLUMNS: { key: NetworkColumnKey; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "position", label: "Current role" },
  { key: "current_company", label: "Current company" },
  { key: "connected_on", label: "Connected on" },
  { key: "category", label: "Reviewer type" },
  { key: "message_action", label: "Copy message" },
  { key: "outreach_status", label: "Outreach status" },
  { key: "last_contacted", label: "Last contacted" },
  { key: "notes", label: "Notes" },
  { key: "relevance_reason", label: "Why relevant" },
  { key: "relevance_score", label: "Relevance score" },
  { key: "registry_company", label: "Registry company" },
  { key: "registry_category", label: "Registry category" },
  { key: "referral_status", label: "Referral status" },
  { key: "match_method", label: "Match method" },
  { key: "official_careers_page", label: "Official careers page" },
  { key: "direct_job_portal", label: "Direct job portal" },
  { key: "email_address", label: "Email address" },
];

function storedText(key: string, fallback: string): string {
  try {
    const stored = window.localStorage.getItem(key);
    if (key === GREETING_STORAGE_KEY && stored === LEGACY_SINGLE_LINE_GREETING) {
      return fallback;
    }
    return stored ?? fallback;
  } catch {
    return fallback;
  }
}

function storedOutreach(): OutreachState {
  try {
    const value = window.localStorage.getItem(OUTREACH_STORAGE_KEY);
    return value ? (JSON.parse(value) as OutreachState) : {};
  } catch {
    return {};
  }
}

function emptyResult(): NetworkConnectionsResponse {
  return {
    rows: [],
    total_matching: 0,
    offset: 0,
    limit: PAGE_SIZE,
    all_connections: 0,
    all_profiles: 0,
    email_connections: 0,
    recommended_profiles: 0,
    leadership_profiles: 0,
    categories: [],
    target_roles: DEFAULT_TARGET_ROLES,
    source: "offline_linkedin_export",
  };
}

function personalize(template: string, connection: NetworkConnectionRow): string {
  const replacements: Record<string, string> = {
    first_name: connection.first_name || connection.name.split(/\s+/)[0] || "there",
    name: connection.name || "there",
    company: connection.current_company || connection.registry_company || "your organization",
    position: connection.position || "your current role",
    connected_on: connection.connected_on || "",
  };
  return template.replace(
    /\{(first_name|name|company|position|connected_on)\}/g,
    (_, key: string) => replacements[key] ?? "",
  );
}

function completeMessage(
  connection: NetworkConnectionRow,
  greetingTemplate: string,
  messageBody: string,
): string {
  return [personalize(greetingTemplate, connection), personalize(messageBody, connection)]
    .map((part) => part.trim())
    .filter(Boolean)
    .join("\n\n");
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Use the local selection fallback when clipboard permission is unavailable.
    }
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

export default function NetworkReviewsTab({
  onNotice,
}: {
  onNotice: (notice: Notice | null) => void;
}) {
  const [result, setResult] = useState<NetworkConnectionsResponse>(emptyResult());
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [recommendedOnly, setRecommendedOnly] = useState(false);
  const [leadershipOnly, setLeadershipOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState("");
  const [greetingTemplate, setGreetingTemplate] = useState(() =>
    storedText(GREETING_STORAGE_KEY, DEFAULT_GREETING),
  );
  const [messageBody, setMessageBody] = useState(() =>
    storedText(BODY_STORAGE_KEY, DEFAULT_BODY),
  );
  const [outreach, setOutreach] = useState<OutreachState>(storedOutreach);
  const [visibleColumns, setVisibleColumns] = useState<NetworkColumnKey[]>(() =>
    NETWORK_COLUMNS.map((column) => column.key),
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(GREETING_STORAGE_KEY, greetingTemplate);
      window.localStorage.setItem(BODY_STORAGE_KEY, messageBody);
    } catch {
      // The current template still works when browser storage is unavailable.
    }
  }, [greetingTemplate, messageBody]);

  useEffect(() => {
    try {
      window.localStorage.setItem(OUTREACH_STORAGE_KEY, JSON.stringify(outreach));
    } catch {
      // Edits remain available for this page session when storage is unavailable.
    }
  }, [outreach]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      api.networkConnections({
        query,
        category,
        recommendedOnly,
        leadershipOnly,
        targetRoles: DEFAULT_TARGET_ROLES,
        offset,
        limit: PAGE_SIZE,
      })
        .then((response) => {
          if (active) setResult(response);
        })
        .catch((error: Error) => {
          if (active) onNotice({ kind: "error", text: error.message });
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query, category, recommendedOnly, leadershipOnly, offset, onNotice]);

  const pageNumber = Math.floor(result.offset / result.limit) + 1;
  const pageCount = Math.max(1, Math.ceil(result.total_matching / result.limit));
  const rangeText = useMemo(() => {
    if (!result.total_matching) return "0 connections";
    const start = result.offset + 1;
    const end = Math.min(result.offset + result.rows.length, result.total_matching);
    return `${start.toLocaleString()}-${end.toLocaleString()} of ${result.total_matching.toLocaleString()}`;
  }, [result]);
  const previewConnection = result.rows[0] ?? null;
  const previewMessage = previewConnection
    ? completeMessage(previewConnection, greetingTemplate, messageBody)
    : "Connection preview will appear after the list loads.";

  const updateOutreach = (
    connectionId: string,
    field: keyof OutreachRecord,
    value: string,
  ) => {
    setOutreach((current) => ({
      ...current,
      [connectionId]: {
        status: current[connectionId]?.status ?? "Not contacted",
        last_contacted: current[connectionId]?.last_contacted ?? "",
        notes: current[connectionId]?.notes ?? "",
        [field]: value,
      },
    }));
  };

  const toggleColumn = (column: NetworkColumnKey) => {
    setVisibleColumns((current) =>
      current.includes(column)
        ? current.filter((item) => item !== column)
        : NETWORK_COLUMNS.map((item) => item.key).filter(
            (item) => current.includes(item) || item === column,
          ),
    );
  };

  const resetTemplates = () => {
    if (!window.confirm("Reset both message boxes to the approved default template?")) return;
    setGreetingTemplate(DEFAULT_GREETING);
    setMessageBody(DEFAULT_BODY);
  };

  const copyMessage = async (connection: NetworkConnectionRow) => {
    try {
      await copyText(completeMessage(connection, greetingTemplate, messageBody));
      setCopiedId(connection.connection_id);
      onNotice({ kind: "success", text: `Message for ${connection.first_name} copied.` });
      window.setTimeout(() => setCopiedId(""), 1800);
    } catch (error) {
      onNotice({ kind: "error", text: (error as Error).message });
    }
  };

  return (
    <main className="network-page">
      <section className="network-intro">
        <div>
          <p className="eyebrow">Offline LinkedIn export</p>
          <h2>Network reviews</h2>
          <p>
            Review every saved connection, open their LinkedIn profile, and copy a personalized
            message without an LLM or LinkedIn scraping.
          </p>
        </div>
        <span className="safe-badge">Private local data</span>
      </section>

      <section className="network-controls network-template-section">
        <div className="network-template-heading">
          <div>
            <p className="eyebrow">Shared outreach template</p>
            <h3>Build the message once</h3>
          </div>
          <button className="secondary-button" type="button" onClick={resetTemplates}>
            Reset template
          </button>
        </div>

        <div className="network-template-grid">
          <label className="field">
            <span>Personalized greeting</span>
            <textarea
              rows={4}
              maxLength={800}
              value={greetingTemplate}
              onChange={(event) => setGreetingTemplate(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Common message body</span>
            <textarea
              rows={10}
              maxLength={5000}
              value={messageBody}
              onChange={(event) => setMessageBody(event.target.value)}
            />
          </label>
        </div>
        <p className="template-help">
          Available placeholders: <code>{"{first_name}"}</code>, <code>{"{name}"}</code>,{" "}
          <code>{"{company}"}</code>, <code>{"{position}"}</code>, and{" "}
          <code>{"{connected_on}"}</code>. Changes are saved in this browser.
        </p>
        <article className="network-template-preview">
          <strong>
            {previewConnection ? `Preview for ${previewConnection.name}` : "Message preview"}
          </strong>
          <p>{previewMessage}</p>
        </article>
      </section>

      <section className="network-controls">
        <div className="network-filter-row">
          <label className="search-field">
            <span>⌕</span>
            <input
              value={query}
              placeholder="Search name, company, role, category, or email…"
              onChange={(event) => {
                setOffset(0);
                setQuery(event.target.value);
              }}
            />
          </label>
          <select
            value={category}
            aria-label="Filter network category"
            onChange={(event) => {
              setOffset(0);
              setCategory(event.target.value);
            }}
          >
            <option value="">All role categories</option>
            {result.categories.map((item) => <option key={item}>{item}</option>)}
          </select>
          <label className="toggle-row compact">
            <input
              type="checkbox"
              checked={recommendedOnly}
              onChange={(event) => {
                setOffset(0);
                setRecommendedOnly(event.target.checked);
              }}
            />
            <span>Recommended only</span>
          </label>
          <label className="toggle-row compact">
            <input
              type="checkbox"
              checked={leadershipOnly}
              onChange={(event) => {
                setOffset(0);
                setLeadershipOnly(event.target.checked);
              }}
            />
            <span>Managers/leads only</span>
          </label>
          <details className="column-picker network-column-picker">
            <summary>Columns · {visibleColumns.length}/{NETWORK_COLUMNS.length}</summary>
            <div>
              <button
                className="column-show-all"
                type="button"
                onClick={() => setVisibleColumns(NETWORK_COLUMNS.map((item) => item.key))}
              >
                Show all
              </button>
              {NETWORK_COLUMNS.map((column) => (
                <label key={column.key}>
                  <input
                    type="checkbox"
                    checked={visibleColumns.includes(column.key)}
                    onChange={() => toggleColumn(column.key)}
                  />
                  <span>{column.label}</span>
                </label>
              ))}
            </div>
          </details>
        </div>
      </section>

      <section className="metrics-grid network-metrics">
        <article className="metric-card"><span>Connections</span><strong>{result.all_connections.toLocaleString()}</strong></article>
        <article className="metric-card"><span>LinkedIn links</span><strong>{result.all_profiles.toLocaleString()}</strong></article>
        <article className="metric-card"><span>Email addresses</span><strong>{result.email_connections.toLocaleString()}</strong></article>
        <article className="metric-card"><span>Recommended</span><strong>{result.recommended_profiles.toLocaleString()}</strong></article>
        <article className="metric-card"><span>Managers/leads</span><strong>{result.leadership_profiles.toLocaleString()}</strong></article>
        <article className="metric-card accent"><span>Current results</span><strong>{result.total_matching.toLocaleString()}</strong></article>
      </section>

      <section className="network-results">
        <div className="network-results-heading">
          <div>
            <h3>Connections</h3>
            <p>{rangeText} · all columns are visible initially</p>
          </div>
          <div className="pagination-controls">
            <button
              className="secondary-button"
              type="button"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <span>Page {pageNumber} of {pageCount}</span>
            <button
              className="secondary-button"
              type="button"
              disabled={offset + result.limit >= result.total_matching || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        </div>

        <div className="table-wrap network-table-wrap" aria-busy={loading}>
          <table className="network-table network-all-columns">
            <thead>
              <tr>
                {visibleColumns.map((key) => (
                  <th key={key}>{NETWORK_COLUMNS.find((column) => column.key === key)?.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((connection) => (
                <tr key={connection.connection_id}>
                  {visibleColumns.map((column) => (
                    <NetworkCell
                      key={column}
                      column={column}
                      connection={connection}
                      outreach={outreach[connection.connection_id]}
                      copied={copiedId === connection.connection_id}
                      onCopy={() => copyMessage(connection)}
                      onOutreachChange={(field, value) =>
                        updateOutreach(connection.connection_id, field, value)
                      }
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && !result.rows.length && <div className="empty-table">No connections match these filters.</div>}
          {loading && <div className="network-loading">Loading offline connections…</div>}
        </div>
        <p className="table-help">
          Exported roles and contact details may be outdated. Verify the LinkedIn profile or email
          before contacting someone; relevance ranking does not imply willingness to help.
        </p>
      </section>
    </main>
  );
}

function NetworkCell({
  column,
  connection,
  outreach,
  copied,
  onCopy,
  onOutreachChange,
}: {
  column: NetworkColumnKey;
  connection: NetworkConnectionRow;
  outreach?: OutreachRecord;
  copied: boolean;
  onCopy: () => void;
  onOutreachChange: (field: keyof OutreachRecord, value: string) => void;
}) {
  if (column === "name") {
    return (
      <td className="network-name-cell">
        {connection.linkedin_profile ? (
          <a className="job-link" href={connection.linkedin_profile} target="_blank" rel="noreferrer">
            {connection.name} ↗
          </a>
        ) : (
          <span>{connection.name}</span>
        )}
      </td>
    );
  }
  if (column === "message_action") {
    return (
      <td className="network-action-cell">
        <button type="button" onClick={onCopy}>{copied ? "Copied" : "Copy message"}</button>
      </td>
    );
  }
  if (column === "outreach_status") {
    return (
      <td>
        <select
          value={outreach?.status ?? "Not contacted"}
          onChange={(event) => onOutreachChange("status", event.target.value)}
        >
          {[
            "Not contacted",
            "Ready",
            "Sent",
            "Replied",
            "Follow-up",
            "Closed",
          ].map((status) => <option key={status}>{status}</option>)}
        </select>
      </td>
    );
  }
  if (column === "last_contacted") {
    return (
      <td>
        <input
          className="network-date-input"
          type="date"
          value={outreach?.last_contacted ?? ""}
          onChange={(event) => onOutreachChange("last_contacted", event.target.value)}
        />
      </td>
    );
  }
  if (column === "notes") {
    return (
      <td>
        <textarea
          className="network-notes-input"
          rows={2}
          value={outreach?.notes ?? ""}
          placeholder="Add note"
          onChange={(event) => onOutreachChange("notes", event.target.value)}
        />
      </td>
    );
  }
  if (column === "category") {
    return <td><span className="value-chip">{connection.category}</span></td>;
  }
  if (column === "email_address") {
    return (
      <td className="network-email-cell">
        {connection.email_address ? (
          <a href={`mailto:${connection.email_address}`}>{connection.email_address}</a>
        ) : <span className="muted">Not supplied</span>}
      </td>
    );
  }
  if (column === "official_careers_page" || column === "direct_job_portal") {
    const url = connection[column];
    return (
      <td>
        {url ? (
          <a className="job-link" href={url} target="_blank" rel="noreferrer">
            {column === "official_careers_page" ? "Open careers" : "Open jobs"} ↗
          </a>
        ) : <span className="muted">Not available</span>}
      </td>
    );
  }

  const value = String(connection[column as keyof NetworkConnectionRow] ?? "");
  return (
    <td className={column === "relevance_reason" ? "network-reason-cell" : ""}>
      {value || <span className="muted">Not supplied</span>}
    </td>
  );
}
