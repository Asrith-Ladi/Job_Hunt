import { useMemo, useState } from "react";
import type { CompanyRegistryEntry, RegistryStatus } from "./types";

const COMPANY_CATEGORIES = [
  "MNC",
  "Product Companies",
  "Startups",
  "Mid-Sized Companies",
  "Other Companies",
] as const;

function verificationTone(status: string): "success" | "warning" | "danger" | "neutral" {
  const normalized = status.trim().toLocaleLowerCase();
  if (normalized.startsWith("accessible")) return "success";
  if (normalized.startsWith("inaccessible")) return "danger";
  if (normalized.startsWith("manual")) return "warning";
  return "neutral";
}

function compactStatus(status: string): string {
  const normalized = status.trim();
  if (!normalized) return "Not checked";
  if (normalized.startsWith("Accessible")) return "Accessible";
  if (normalized.startsWith("Inaccessible")) return "Inaccessible";
  if (normalized.startsWith("Manual required")) return "Manual review";
  return normalized;
}

function sourceLabel(entry: CompanyRegistryEntry): string {
  return entry.detection.provider && entry.detection.provider !== "generic"
    ? entry.detection.provider
    : entry.source_type_label || "Company page";
}

export default function CompanyRegistryTab({
  registry,
  registryStatus,
  refreshingRegistry,
  selectedCompanyIds,
  maximumSelected,
  onSelectionChange,
  onRefreshRegistry,
  onUseSelected,
}: {
  registry: CompanyRegistryEntry[];
  registryStatus: RegistryStatus | null;
  refreshingRegistry: boolean;
  selectedCompanyIds: string[];
  maximumSelected: number;
  onSelectionChange: (companyIds: string[]) => void;
  onRefreshRegistry: () => void;
  onUseSelected: () => void;
}) {
  const [activeCategory, setActiveCategory] = useState<string>(COMPANY_CATEGORIES[0]);
  const [query, setQuery] = useState("");
  const selected = useMemo(() => new Set(selectedCompanyIds), [selectedCompanyIds]);
  const counts = useMemo(() => {
    const result = new Map<string, number>();
    registry.forEach((entry) => result.set(entry.category, (result.get(entry.category) ?? 0) + 1));
    return result;
  }, [registry]);
  const activeRows = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return registry
      .filter((entry) => entry.category === activeCategory)
      .filter((entry) => !needle || [
        entry.company,
        entry.sector,
        entry.priority,
        entry.source_type_label,
        entry.detection.provider,
        entry.india_jobs,
        entry.verification_status,
      ].some((value) => value.toLocaleLowerCase().includes(needle)))
      .sort((left, right) => left.company.localeCompare(right.company));
  }, [activeCategory, query, registry]);
  const accessibleCount = registry.filter((entry) => entry.verification_status.startsWith("Accessible")).length;
  const manualCount = registry.filter((entry) => entry.verification_status.startsWith("Manual required")).length;
  const activeRowIds = activeRows.map((entry) => entry.company_id);
  const selectedInActiveArea = activeRowIds.filter((companyId) => selected.has(companyId)).length;
  const remainingSelectionSlots = Math.max(0, maximumSelected - selectedCompanyIds.length);

  const toggleCompany = (companyId: string) => {
    if (selected.has(companyId)) {
      onSelectionChange(selectedCompanyIds.filter((item) => item !== companyId));
      return;
    }
    if (selectedCompanyIds.length < maximumSelected) {
      onSelectionChange([...selectedCompanyIds, companyId]);
    }
  };

  const selectAllInActiveArea = () => {
    if (!remainingSelectionSlots) return;
    const additions = activeRowIds
      .filter((companyId) => !selected.has(companyId))
      .slice(0, remainingSelectionSlots);
    onSelectionChange([...selectedCompanyIds, ...additions]);
  };

  const clearActiveArea = () => {
    const activeIds = new Set(activeRowIds);
    onSelectionChange(selectedCompanyIds.filter((companyId) => !activeIds.has(companyId)));
  };

  return (
    <main className="product-page company-registry-page">
      <section className="page-intro company-registry-intro">
        <div>
          <p className="eyebrow">Official employer directory</p>
          <h2>Open the right careers page without searching for it again.</h2>
          <p>
            Browse the five registry groups, open verified employer links, and choose companies
            for your next Company Portal search.
          </p>
        </div>
        <div className="registry-page-actions">
          {registryStatus?.drive_url && (
            <a className="secondary-button" href={registryStatus.drive_url} target="_blank" rel="noreferrer">
              Open registry in Drive ↗
            </a>
          )}
          <button className="secondary-button" type="button" onClick={onRefreshRegistry} disabled={refreshingRegistry}>
            {refreshingRegistry ? "Refreshing…" : "Refresh from Drive"}
          </button>
        </div>
      </section>

      <section className="company-registry-metrics" aria-label="Registry summary">
        <article><small>Companies</small><strong>{registry.length}</strong><span>One primary category each</span></article>
        <article><small>Directly accessible</small><strong>{accessibleCount}</strong><span>Public page responded</span></article>
        <article><small>Manual or company-specific</small><strong>{manualCount}</strong><span>Browser review may be needed</span></article>
        <article className="selected"><small>Selected for search</small><strong>{selectedCompanyIds.length}</strong><span>Maximum {maximumSelected} per run</span></article>
      </section>

      <section className="company-registry-workspace">
        <header className="company-registry-toolbar">
          <label className="search-field company-registry-search">
            <span aria-hidden="true">⌕</span>
            <input
              value={query}
              placeholder="Search this group by company, sector, provider, or status…"
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="registry-bulk-controls">
            <span>{selectedInActiveArea}/{activeRows.length} selected here</span>
            <button
              type="button"
              onClick={selectAllInActiveArea}
              disabled={!activeRows.length || !remainingSelectionSlots || selectedInActiveArea === activeRows.length}
              title={`Select every shown company that fits within the ${maximumSelected}-company search limit`}
            >
              Select all shown
            </button>
            <button type="button" onClick={clearActiveArea} disabled={!selectedInActiveArea}>
              Clear area
            </button>
          </div>
          <button
            className="primary-button"
            type="button"
            disabled={!selectedCompanyIds.length}
            onClick={onUseSelected}
          >
            Continue with {selectedCompanyIds.length || 0} selected
          </button>
        </header>

        <div className="company-category-tabs" role="tablist" aria-label="Company registry categories">
          {COMPANY_CATEGORIES.map((category) => (
            <button
              id={`company-category-${category.replaceAll(" ", "-").toLocaleLowerCase()}`}
              type="button"
              role="tab"
              aria-selected={activeCategory === category}
              className={activeCategory === category ? "active" : ""}
              onClick={() => setActiveCategory(category)}
              key={category}
            >
              <span>{category}</span>
              <b>{counts.get(category) ?? 0}</b>
            </button>
          ))}
        </div>

        <div className="company-registry-source-note">
          <div>
            <strong>{registryStatus?.source === "google_drive" ? "Drive registry" : "Validated local cache"}</strong>
            <span>{registryStatus?.warning || "The detailed workbook remains the source of truth for company data."}</span>
          </div>
          {registryStatus?.drive_modified_time && <time>Updated {new Date(registryStatus.drive_modified_time).toLocaleString()}</time>}
        </div>

        <div
          className="table-wrap company-registry-table-wrap"
          role="tabpanel"
          aria-labelledby={`company-category-${activeCategory.replaceAll(" ", "-").toLocaleLowerCase()}`}
        >
          <table className="company-registry-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Sector</th>
                <th>Priority</th>
                <th>Official careers</th>
                <th>Direct job portal</th>
                <th>Provider</th>
                <th>India jobs</th>
                <th>Verification</th>
                <th>Search</th>
              </tr>
            </thead>
            <tbody>
              {activeRows.map((entry) => {
                const isSelected = selected.has(entry.company_id);
                const selectionCapped = !isSelected && selectedCompanyIds.length >= maximumSelected;
                return (
                  <tr key={entry.company_id}>
                    <td className="company-registry-name">
                      <strong>{entry.company}</strong>
                      <small>{entry.category}</small>
                    </td>
                    <td>{entry.sector || "—"}</td>
                    <td><span className={`registry-priority ${entry.priority.toLocaleLowerCase()}`}>{entry.priority || "—"}</span></td>
                    <td>
                      <a className="registry-link" href={entry.careers_url} target="_blank" rel="noreferrer">
                        Open careers ↗
                      </a>
                    </td>
                    <td>
                      <a className="registry-link" href={entry.portal_url} target="_blank" rel="noreferrer">
                        Search jobs ↗
                      </a>
                    </td>
                    <td>
                      <span className={`registry-provider ${entry.adapter_ready ? "structured" : "public"}`}>
                        {sourceLabel(entry)}
                      </span>
                    </td>
                    <td>{entry.india_jobs || "Global search"}</td>
                    <td>
                      <span className={`registry-verification ${verificationTone(entry.verification_status)}`} title={entry.verification_status}>
                        {compactStatus(entry.verification_status)}
                      </span>
                    </td>
                    <td>
                      <button
                        className={`registry-select-action ${isSelected ? "selected" : ""}`}
                        type="button"
                        disabled={selectionCapped}
                        aria-pressed={isSelected}
                        onClick={() => toggleCompany(entry.company_id)}
                      >
                        {isSelected ? "Selected ✓" : "Select"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!activeRows.length && (
                <tr><td className="company-registry-empty" colSpan={9}>No companies match this group and search.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
