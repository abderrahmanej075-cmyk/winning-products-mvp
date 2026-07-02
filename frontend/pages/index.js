import { useEffect, useState } from "react";

const API = "http://localhost:8000";

const VERDICT_COLOR = {
  "Reject": "#e5484d",
  "Watchlist": "#f5a623",
  "Test with small budget": "#4a90d9",
  "Strong candidate": "#46a758",
};

const PIPELINE_STATUSES = [
  { key: "new",            label: "New",            color: "#7d8896" },
  { key: "researching",    label: "Researching",    color: "#f5a623" },
  { key: "test_candidate", label: "Test Candidate", color: "#4a90d9" },
  { key: "winner",         label: "Winner",         color: "#46a758" },
  { key: "rejected",       label: "Rejected",       color: "#e5484d" },
];

// Fields offered in the manual-input form. type: text | number | select
const FORM_FIELDS = [
  { k: "name", label: "Product name", type: "text", required: true },
  { k: "category", label: "Category", type: "select",
    options: ["health", "beauty", "home", "kitchen", "fitness", "pets", "auto", "toys", "cosmetics", "other"] },
  { k: "country", label: "Country", type: "text", placeholder: "US" },
  { k: "retail_price", label: "Retail price ($)", type: "number" },
  { k: "supplier_cost", label: "Supplier cost ($)", type: "number" },
  { k: "shipping_cost", label: "Shipping cost ($)", type: "number" },
  { k: "product_weight_kg", label: "Weight (kg)", type: "number" },
  { k: "trends_interest", label: "Google Trends interest (0-100)", type: "number" },
  { k: "trends_direction_pct", label: "Trends 12-mo change (%)", type: "number" },
  { k: "seasonality_ratio", label: "Seasonality peak/trough ratio", type: "number" },
  { k: "amazon_bsr", label: "Amazon Best Sellers Rank", type: "number" },
  { k: "tiktok_hashtag_views", label: "TikTok hashtag views", type: "number" },
  { k: "tiktok_momentum", label: "TikTok momentum", type: "select",
    options: ["", "trending", "rising", "flat", "declining"] },
  { k: "meta_active_advertisers", label: "Meta active advertisers", type: "number" },
  { k: "aliexpress_sellers_1k", label: "AliExpress sellers w/ 1k+ orders", type: "number" },
  { k: "competitor_count", label: "Amazon competitor count", type: "number" },
  { k: "diff_complement_skus", label: "Complementary SKUs (bundling)", type: "number" },
  { k: "alltime_current_value", label: "Trends all-time current value (fad check)", type: "number" },
];

function Pill({ verdict }) {
  return (
    <span className="pill" style={{ background: VERDICT_COLOR[verdict] || "#666" }}>
      {verdict}
    </span>
  );
}

export default function Home() {
  const [products, setProducts] = useState([]);
  const [report, setReport] = useState(null);
  const [detail, setDetail] = useState(null);
  const [form, setForm] = useState({ category: "other", country: "US" });
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const [discSeed, setDiscSeed] = useState("posture corrector");
  const [discCountry, setDiscCountry] = useState("US");
  const [discResults, setDiscResults] = useState(null);
  const [discLoading, setDiscLoading] = useState(false);
  const [discError, setDiscError] = useState("");

  // Discovered eBay Products — sort and filter state
  const [ebaySort, setEbaySort] = useState("newest");
  const [ebayFilterRec, setEbayFilterRec] = useState("");
  const [ebayFilterLink, setEbayFilterLink] = useState(false);
  const [ebayFilterCountry, setEbayFilterCountry] = useState("");
  const [ebayFilterShortlisted, setEbayFilterShortlisted] = useState(false);
  const [reviewDrafts, setReviewDrafts] = useState({});

  async function saveReviewStatus(prodId, status) {
    await fetch(`${API}/products/${prodId}/review`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_status: status }),
    });
    await load();
  }

  async function saveReviewNotes(prodId) {
    const notes = reviewDrafts[prodId] !== undefined ? reviewDrafts[prodId] : "";
    await fetch(`${API}/products/${prodId}/review`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operator_notes: notes }),
    });
    setReviewDrafts((d) => { const n = { ...d }; delete n[prodId]; return n; });
    await load();
  }

  async function toggleShortlist(pid, e) {
    e.stopPropagation();
    await fetch(`${API}/products/${pid}/shortlist`, { method: "POST" });
    await load();
  }

  async function load() {
    setError("");
    try {
      const [pr, rp] = await Promise.all([
        fetch(`${API}/products`).then((r) => r.json()),
        fetch(`${API}/reports/daily`).then((r) => r.json()),
      ]);
      setProducts(pr);
      setReport(rp);
    } catch (e) {
      setError("Can't reach the API at " + API + ". Is the backend running on port 8000?");
    }
  }

  useEffect(() => { load(); }, []);

  async function openDetail(id) {
    setDetail({ loading: true });
    try {
      const d = await fetch(`${API}/products/${id}`).then((r) => r.json());
      setDetail(d);
    } catch (e) {
      setDetail(null);
      setError("Failed to load product detail.");
    }
  }

  function setField(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function runEbayDiscovery(e) {
    e.preventDefault();
    setDiscError("");
    setDiscLoading(true);
    setDiscResults(null);
    try {
      const res = await fetch(`${API}/discovery/multisource`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seeds: [discSeed],
          country: discCountry || "US",
          sources: ["ebay"],
        }),
      }).then((r) => r.json());
      setDiscResults(res);
      await load(); // refresh products table with newly saved eBay candidates
    } catch (e) {
      setDiscError("eBay discovery search failed. Is the backend running on port 8000?");
    }
    setDiscLoading(false);
  }

  async function submit(e) {
    e.preventDefault();
    setStatus("Scoring...");
    setError("");
    const payload = {};
    for (const f of FORM_FIELDS) {
      const v = form[f.k];
      if (v !== undefined && v !== null && String(v).trim() !== "") payload[f.k] = String(v).trim();
    }
    if (!payload.name) { setError("Product name is required."); setStatus(""); return; }
    try {
      const res = await fetch(`${API}/discovery/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then((r) => r.json());
      setStatus(`Added "${res.product.name}" -> ${res.scoring.recommendation}` +
        (res.scoring.score != null ? ` (${res.scoring.score}/60)` : ""));
      setForm({ category: "other", country: "US" });
      await load();
      await openDetail(res.id);
    } catch (e) {
      setError("Failed to add product.");
      setStatus("");
    }
  }

  // Shortlisted products — across all sources, sorted by shortlisted_at desc
  const shortlistedProducts = products
    .filter((p) => !!p.shortlisted)
    .sort((a, b) => (b.shortlisted_at || "").localeCompare(a.shortlisted_at || ""));

  // Derived data for the Discovered eBay Products panel
  const allEbayProducts = products.filter((p) => p.source === "ebay");
  const ebayRecs = [...new Set(allEbayProducts.map((p) => p.recommendation).filter(Boolean))].sort();
  const ebayCountries = [...new Set(allEbayProducts.map((p) => p.country).filter(Boolean))].sort();
  const visibleEbay = allEbayProducts
    .filter((p) => !ebayFilterRec || p.recommendation === ebayFilterRec)
    .filter((p) => !ebayFilterLink || !!p.source_url)
    .filter((p) => !ebayFilterCountry || p.country === ebayFilterCountry)
    .filter((p) => !ebayFilterShortlisted || !!p.shortlisted)
    .sort((a, b) => {
      if (ebaySort === "newest") return (b.discovered_at || "").localeCompare(a.discovered_at || "");
      if (ebaySort === "score")  return (b.score ?? -1) - (a.score ?? -1);
      if (ebaySort === "price_asc")  return (a.retail_price ?? Infinity) - (b.retail_price ?? Infinity);
      if (ebaySort === "price_desc") return (b.retail_price ?? -1) - (a.retail_price ?? -1);
      return 0;
    });
  const ebayFiltersActive = !!(ebayFilterRec || ebayFilterLink || ebayFilterCountry || ebayFilterShortlisted);

  return (
    <main>
      <header>
        <div>
          <h1>Winning Products</h1>
          <p className="sub">Local MVP · scoring spec V2 · sample data · no external APIs yet</p>
        </div>
        {report && (
          <div className="stats">
            <Stat label="Products" value={report.total_products} />
            <Stat label="Eliminated" value={report.eliminated} />
            <Stat label="Avg score" value={report.average_score ?? "—"} />
            <Stat label="Test+" value={(report.by_recommendation["Test with small budget"] || 0) + (report.by_recommendation["Strong candidate"] || 0)} />
          </div>
        )}
      </header>

      {error && <div className="error">{error}</div>}

      <section className="panel" style={{ marginTop: 20 }}>
        <h2>eBay Discovery</h2>
        <form onSubmit={runEbayDiscovery} className="discform">
          <label className="field">
            <span>Seed keyword</span>
            <input
              type="text"
              value={discSeed}
              onChange={(e) => setDiscSeed(e.target.value)}
              placeholder="posture corrector"
            />
          </label>
          <label className="field">
            <span>Country</span>
            <input
              type="text"
              value={discCountry}
              onChange={(e) => setDiscCountry(e.target.value)}
              placeholder="US"
            />
          </label>
          <label className="field">
            <span>Source</span>
            <select value="ebay" disabled>
              <option value="ebay">eBay</option>
            </select>
          </label>
          <button type="submit" disabled={discLoading}>
            {discLoading ? "Searching…" : "Search eBay"}
          </button>
        </form>

        {discError && <div className="error">{discError}</div>}

        {discResults && (
          <>
            <p className="muted" style={{ fontSize: 12.5, margin: "12px 0 8px" }}>
              {(discResults.candidates || []).length} candidate(s)
              {discResults.source_breakdown && Object.keys(discResults.source_breakdown).length > 0 && (
                <>
                  {" "}· source:{" "}
                  {Object.entries(discResults.source_breakdown)
                    .map(([s, n]) => `${s} (${n})`)
                    .join(", ")}
                </>
              )}
            </p>
            {discResults.missing_sources && discResults.missing_sources.length > 0 && (
              <div className="reason">
                {discResults.missing_sources.map((m) => m.note).join(" ")}
              </div>
            )}
            <div className="disc-grid">
              {(discResults.candidates || []).map((c, i) => (
                <div className="disc-card" key={i}>
                  <div className="disc-title">{c.name}</div>
                  <div className="disc-row">
                    <span className="muted">
                      {c.retail_price != null ? `$${c.retail_price}` : "price n/a"}
                    </span>
                    <span className="srcpill">{c.source}</span>
                  </div>
                  {c.source_url ? (
                    <a href={c.source_url} target="_blank" rel="noreferrer" className="disc-link">
                      View on eBay →
                    </a>
                  ) : (
                    <span className="muted" style={{ fontSize: 11.5 }}>link not available</span>
                  )}
                  {c.score != null && (
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>
                      Score: {c.score}/60
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {/* Shortlisted Products — review cards, shown only when at least one product is shortlisted */}
      {shortlistedProducts.length > 0 && (
        <section className="panel" style={{ marginTop: 20, borderColor: "#3a4a2a" }}>
          <h2 style={{ color: "#f5c518" }}>
            ★ Shortlisted Products
            <span className="count-badge" style={{ background: "#2a3018", color: "#f5c518" }}>
              {shortlistedProducts.length}
            </span>
          </h2>
          <div className="sl-cards">
            {shortlistedProducts.map((p) => (
              <div key={p.id} className="sl-card" onClick={() => openDetail(p.id)}>
                <div className="sl-card-top">
                  <div className="sl-card-name">
                    <span className="srcpill">{p.source || "manual"}</span>
                    {p.name}
                  </div>
                  <div className="sl-card-meta">
                    {p.retail_price != null && <span>${p.retail_price}</span>}
                    {p.score != null && <span>{p.score}/60</span>}
                    <Pill verdict={p.recommendation} />
                  </div>
                </div>

                {p.source_url && (
                  <a
                    href={p.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="disc-link"
                    style={{ fontSize: 12, display: "inline-block", marginBottom: 8 }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    View on {p.source === "ebay" ? "eBay" : "source"} →
                  </a>
                )}

                <div className="sl-card-review" onClick={(e) => e.stopPropagation()}>
                  <select
                    className={`sl-status-select sl-status-${p.review_status || "new"}`}
                    value={p.review_status || "new"}
                    onChange={(e) => saveReviewStatus(p.id, e.target.value)}
                  >
                    <option value="new">New</option>
                    <option value="researching">Researching</option>
                    <option value="test_candidate">Test candidate</option>
                    <option value="rejected">Rejected</option>
                    <option value="winner">Winner ★</option>
                  </select>
                  <input
                    type="text"
                    className="sl-notes-input"
                    placeholder="Operator notes…"
                    value={reviewDrafts[p.id] !== undefined ? reviewDrafts[p.id] : (p.operator_notes || "")}
                    onChange={(e) => setReviewDrafts((d) => ({ ...d, [p.id]: e.target.value }))}
                  />
                  <button className="sl-notes-save" onClick={() => saveReviewNotes(p.id)}>
                    Save
                  </button>
                </div>

                {p.operator_notes && reviewDrafts[p.id] === undefined && (
                  <p className="sl-saved-note">{p.operator_notes}</p>
                )}

                <div className="sl-card-footer">
                  <span className="muted" style={{ fontSize: 11.5 }}>
                    Shortlisted {p.shortlisted_at ? p.shortlisted_at.slice(0, 10) : ""}
                    {p.reviewed_at && ` · reviewed ${p.reviewed_at.slice(0, 10)}`}
                  </span>
                  <button
                    className="sl-unshortlist"
                    onClick={(e) => toggleShortlist(p.id, e)}
                    title="Remove from shortlist"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Product Review Pipeline — kanban grouped by review_status */}
      {products.length > 0 && (
        <section className="panel" style={{ marginTop: 20 }}>
          <h2>Product Review Pipeline</h2>
          <div className="pipeline">
            {PIPELINE_STATUSES.map(({ key, label, color }) => {
              const group = products.filter((p) => (p.review_status || "new") === key);
              const showAll = key !== "new";
              const shown  = showAll ? group : group.slice(0, 5);
              const hidden = showAll ? 0 : Math.max(0, group.length - 5);
              return (
                <div key={key} className="pipeline-col">
                  <div className="pipeline-col-header" style={{ borderTopColor: color }}>
                    <span className="pipeline-col-label">{label}</span>
                    <span className="pipeline-col-count" style={{ background: color + "22", color }}>
                      {group.length}
                    </span>
                  </div>

                  {shown.map((p) => (
                    <div key={p.id} className="pipeline-card" onClick={() => openDetail(p.id)}>
                      <div className="pipeline-card-name" title={p.name}>
                        {p.shortlisted && <span className="pipeline-star">★</span>}
                        {p.name}
                      </div>
                      <div className="pipeline-card-meta">
                        <span className="srcpill">{p.source || "manual"}</span>
                        {p.retail_price != null && (
                          <span className="muted" style={{ fontSize: 11.5 }}>${p.retail_price}</span>
                        )}
                      </div>
                      {p.recommendation && <Pill verdict={p.recommendation} />}
                      {p.operator_notes && (
                        <p className="pipeline-note">{p.operator_notes}</p>
                      )}
                      <div onClick={(e) => e.stopPropagation()}>
                        <select
                          className={`sl-status-select sl-status-${p.review_status || "new"}`}
                          value={p.review_status || "new"}
                          onChange={(e) => saveReviewStatus(p.id, e.target.value)}
                          style={{ width: "100%", marginTop: 6 }}
                        >
                          {PIPELINE_STATUSES.map(({ key: k, label: l }) => (
                            <option key={k} value={k}>{l}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ))}

                  {hidden > 0 && (
                    <p className="pipeline-more">+{hidden} more in backlog</p>
                  )}
                  {group.length === 0 && (
                    <p className="pipeline-empty">—</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Discovered eBay Products — full-width panel, shown when any eBay products exist */}
      {allEbayProducts.length > 0 && (
        <section className="panel" style={{ marginTop: 20 }}>
          <h2>
            Discovered eBay Products
            <span className="count-badge">{visibleEbay.length}/{allEbayProducts.length}</span>
          </h2>

          {/* Controls bar */}
          <div className="ebay-controls">
            <label className="ctrl-label">
              Sort
              <select value={ebaySort} onChange={(e) => setEbaySort(e.target.value)}>
                <option value="newest">Newest first</option>
                <option value="score">Highest score</option>
                <option value="price_asc">Lowest price</option>
                <option value="price_desc">Highest price</option>
              </select>
            </label>

            {ebayRecs.length > 0 && (
              <label className="ctrl-label">
                Recommendation
                <select value={ebayFilterRec} onChange={(e) => setEbayFilterRec(e.target.value)}>
                  <option value="">All</option>
                  {ebayRecs.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </label>
            )}

            {ebayCountries.length > 1 && (
              <label className="ctrl-label">
                Country
                <select value={ebayFilterCountry} onChange={(e) => setEbayFilterCountry(e.target.value)}>
                  <option value="">All</option>
                  {ebayCountries.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            )}

            <label className="ctrl-check">
              <input
                type="checkbox"
                checked={ebayFilterLink}
                onChange={(e) => setEbayFilterLink(e.target.checked)}
              />
              Has eBay link
            </label>

            <label className="ctrl-check">
              <input
                type="checkbox"
                checked={ebayFilterShortlisted}
                onChange={(e) => setEbayFilterShortlisted(e.target.checked)}
              />
              ★ Shortlisted only
            </label>

            {ebayFiltersActive && (
              <button
                className="ctrl-reset"
                onClick={() => {
                  setEbayFilterRec("");
                  setEbayFilterLink(false);
                  setEbayFilterCountry("");
                  setEbayFilterShortlisted(false);
                }}
              >
                Clear filters
              </button>
            )}
          </div>

          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}></th>
                <th>Product</th>
                <th>Country</th>
                <th className="num">Price</th>
                <th className="num">Score</th>
                <th>Recommendation</th>
                <th>Link</th>
                <th>Discovered</th>
              </tr>
            </thead>
            <tbody>
              {visibleEbay.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted" style={{ textAlign: "center", padding: "16px 0" }}>
                    No products match the current filters.
                  </td>
                </tr>
              ) : (
                visibleEbay.map((p) => (
                  <tr key={p.id} onClick={() => openDetail(p.id)} className={`row${p.shortlisted ? " row-shortlisted" : ""}`}>
                    <td onClick={(e) => e.stopPropagation()} style={{ textAlign: "center" }}>
                      <button
                        className={`star-btn${p.shortlisted ? " star-on" : ""}`}
                        onClick={(e) => toggleShortlist(p.id, e)}
                        title={p.shortlisted ? "Remove from shortlist" : "Add to shortlist"}
                      >
                        {p.shortlisted ? "★" : "☆"}
                      </button>
                    </td>
                    <td>
                      <span className="srcpill" style={{ marginRight: 6 }}>ebay</span>
                      {p.name}
                    </td>
                    <td className="muted">{p.country || "US"}</td>
                    <td className="num muted">
                      {p.retail_price != null ? `$${p.retail_price}` : "—"}
                    </td>
                    <td className="num">{p.score == null ? "—" : `${p.score}/60`}</td>
                    <td><Pill verdict={p.recommendation} /></td>
                    <td>
                      {p.source_url ? (
                        <a
                          href={p.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="disc-link"
                          onClick={(e) => e.stopPropagation()}
                        >
                          View on eBay →
                        </a>
                      ) : (
                        <span className="muted" style={{ fontSize: 11.5 }}>—</span>
                      )}
                    </td>
                    <td className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                      {p.discovered_at ? p.discovered_at.slice(0, 10) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      )}

      <div className="grid">
        <section className="panel">
          <h2>
            Sample / Manual Products
            <span className="count-badge">{products.filter((p) => p.source !== "ebay").length}</span>
          </h2>
          <table>
            <thead>
              <tr>
                <th>Product</th><th>Category</th><th>Country</th>
                <th className="num">Score</th><th>Recommendation</th>
                <th className="num">Net/order</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {products.filter((p) => p.source !== "ebay").map((p) => (
                <tr key={p.id} onClick={() => openDetail(p.id)} className="row">
                  <td>{p.name}</td>
                  <td className="muted">{p.category}</td>
                  <td className="muted">{p.country}</td>
                  <td className="num">{p.score == null ? "—" : `${p.score}/60`}</td>
                  <td><Pill verdict={p.recommendation} /></td>
                  <td className="num">{p.net_profit_per_order == null ? "—" : `$${p.net_profit_per_order}`}</td>
                  <td className="muted">{p.confidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>Add a product</h2>
          <form onSubmit={submit} className="form">
            {FORM_FIELDS.map((f) => (
              <label key={f.k} className="field">
                <span>{f.label}{f.required ? " *" : ""}</span>
                {f.type === "select" ? (
                  <select value={form[f.k] ?? ""} onChange={(e) => setField(f.k, e.target.value)}>
                    {f.options.map((o) => <option key={o} value={o}>{o === "" ? "—" : o}</option>)}
                  </select>
                ) : (
                  <input
                    type={f.type === "number" ? "number" : "text"}
                    step="any"
                    placeholder={f.placeholder || ""}
                    value={form[f.k] ?? ""}
                    onChange={(e) => setField(f.k, e.target.value)}
                  />
                )}
              </label>
            ))}
            <button type="submit">Add &amp; score</button>
            {status && <p className="status">{status}</p>}
            <p className="hint">Leave a field blank and it counts as “Not Measured” — it lowers confidence but never the score.</p>
          </form>
        </section>
      </div>

      {detail && <Detail detail={detail} onClose={() => setDetail(null)} />}

      <style jsx global>{`
        * { box-sizing: border-box; }
        body { margin: 0; background: #0f1419; color: #e6edf3;
          font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
        main { max-width: 1200px; margin: 0 auto; padding: 28px 20px 80px; }
        header { display: flex; justify-content: space-between; align-items: flex-end;
          gap: 20px; flex-wrap: wrap; border-bottom: 1px solid #232b36; padding-bottom: 18px; }
        h1 { margin: 0; font-size: 26px; letter-spacing: -0.02em; }
        .sub { margin: 4px 0 0; color: #7d8896; font-size: 13px; }
        .stats { display: flex; gap: 10px; }
        .stat { background: #161c24; border: 1px solid #232b36; border-radius: 10px;
          padding: 8px 14px; min-width: 78px; }
        .stat .v { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; }
        .stat .l { font-size: 11px; color: #7d8896; text-transform: uppercase; letter-spacing: 0.06em; }
        .grid { display: grid; grid-template-columns: 1fr 360px; gap: 18px; margin-top: 20px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        .panel { background: #131922; border: 1px solid #232b36; border-radius: 14px; padding: 16px 18px; }
        .panel h2 { margin: 0 0 12px; font-size: 15px; color: #c7d0db; font-weight: 600; }
        table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
        th { text-align: left; color: #7d8896; font-weight: 500; font-size: 11px;
          text-transform: uppercase; letter-spacing: 0.05em; padding: 6px 8px; border-bottom: 1px solid #232b36; }
        td { padding: 9px 8px; border-bottom: 1px solid #1b222c; }
        .num { text-align: right; font-variant-numeric: tabular-nums; }
        .muted { color: #8b95a3; }
        .row { cursor: pointer; }
        .row:hover td { background: #19212c; }
        .pill { display: inline-block; padding: 2px 9px; border-radius: 999px;
          font-size: 11px; font-weight: 600; color: #0b0e12; white-space: nowrap; }
        .form { display: flex; flex-direction: column; gap: 10px; }
        .field { display: flex; flex-direction: column; gap: 4px; }
        .field span { font-size: 12px; color: #9aa4b2; }
        input, select { background: #0e141b; border: 1px solid #2a333f; color: #e6edf3;
          border-radius: 8px; padding: 7px 9px; font-size: 13px; }
        input:focus, select:focus { outline: 2px solid #4a90d9; border-color: transparent; }
        button { margin-top: 6px; background: #4a90d9; color: #fff; border: 0; border-radius: 8px;
          padding: 10px; font-size: 14px; font-weight: 600; cursor: pointer; }
        button:hover { background: #3a7fc8; }
        .status { color: #46a758; font-size: 12.5px; margin: 4px 0 0; }
        .hint { color: #7d8896; font-size: 11.5px; margin: 6px 0 0; line-height: 1.4; }
        .error { background: #2a1416; border: 1px solid #5c2327; color: #f4a9ac;
          padding: 10px 14px; border-radius: 10px; margin-top: 16px; font-size: 13px; }
        .drawer { position: fixed; top: 0; right: 0; height: 100vh; width: 460px; max-width: 92vw;
          background: #121821; border-left: 1px solid #232b36; padding: 22px; overflow-y: auto;
          box-shadow: -20px 0 50px rgba(0,0,0,0.4); }
        .drawer h3 { margin: 0 0 2px; font-size: 18px; }
        .close { position: absolute; top: 16px; right: 18px; background: none; color: #8b95a3;
          width: auto; margin: 0; padding: 2px 6px; font-size: 18px; }
        .catrow { display: flex; justify-content: space-between; align-items: center;
          padding: 7px 0; border-bottom: 1px solid #1b222c; font-size: 13.5px; }
        .bar { height: 6px; border-radius: 3px; background: #4a90d9; }
        .barwrap { background: #1b222c; border-radius: 3px; width: 120px; height: 6px; }
        .reason { color: #9aa4b2; font-size: 12.5px; line-height: 1.5; margin-top: 12px;
          background: #0e141b; border: 1px solid #232b36; border-radius: 8px; padding: 10px 12px; }
        .discform { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
        .discform .field { min-width: 160px; }
        .discform button { margin-top: 0; }
        .disc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
          gap: 10px; margin-top: 4px; }
        .disc-card { background: #0e141b; border: 1px solid #232b36; border-radius: 10px; padding: 12px; }
        .disc-title { font-size: 13.5px; font-weight: 600; margin-bottom: 6px; }
        .disc-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
        .srcpill { background: #1b2735; color: #7fb2e8; font-size: 10.5px; font-weight: 600;
          padding: 2px 8px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.04em; }
        .disc-link { color: #4a90d9; font-size: 12.5px; text-decoration: none; }
        .disc-link:hover { text-decoration: underline; }
        .count-badge { display: inline-block; margin-left: 8px; background: #1b2735;
          color: #7fb2e8; font-size: 11px; font-weight: 600; padding: 1px 7px;
          border-radius: 999px; vertical-align: middle; }
        .ebay-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
          margin-bottom: 14px; }
        .ctrl-label { display: flex; flex-direction: column; font-size: 11px; color: #8899aa;
          gap: 3px; }
        .ctrl-label select { font-size: 13px; background: #1b2735; color: #d0e4f7;
          border: 1px solid #2a3d55; border-radius: 5px; padding: 3px 7px; cursor: pointer; }
        .ctrl-check { display: flex; align-items: center; gap: 5px; font-size: 13px;
          color: #8899aa; cursor: pointer; user-select: none; }
        .ctrl-check input[type="checkbox"] { accent-color: #4a90d9; cursor: pointer; }
        .ctrl-reset { background: none; border: 1px solid #2a3d55; color: #7fb2e8;
          font-size: 12px; padding: 3px 10px; border-radius: 5px; cursor: pointer; }
        .ctrl-reset:hover { background: #1b2735; }
        .star-btn { background: none; border: none; font-size: 16px; cursor: pointer;
          color: #4a6070; line-height: 1; padding: 2px 4px; border-radius: 4px;
          transition: color 0.15s, transform 0.1s; }
        .star-btn:hover { color: #f5c518; transform: scale(1.2); }
        .star-btn.star-on { color: #f5c518; }
        .row-shortlisted { background: rgba(245,197,24,0.05); }
        .row-shortlisted:hover { background: rgba(245,197,24,0.1) !important; }
        .sl-unshortlist { background: none; border: 1px solid #4a3a10; color: #c8a000;
          font-size: 11.5px; font-weight: 500; padding: 2px 9px; border-radius: 5px;
          cursor: pointer; margin: 0; white-space: nowrap; }
        .sl-unshortlist:hover { background: #2a2008; border-color: #c8a000; color: #f5c518; }
        .sl-cards { display: flex; flex-direction: column; gap: 10px; }
        .sl-card { background: #0e141b; border: 1px solid #2a3a1a; border-radius: 10px;
          padding: 12px 14px; cursor: pointer; transition: border-color 0.15s; }
        .sl-card:hover { border-color: #4a6a3a; }
        .sl-card-top { display: flex; justify-content: space-between; align-items: flex-start;
          gap: 10px; margin-bottom: 6px; }
        .sl-card-name { font-size: 13.5px; font-weight: 600; display: flex; align-items: center;
          gap: 6px; flex: 1; flex-wrap: wrap; }
        .sl-card-meta { display: flex; align-items: center; gap: 8px; font-size: 12.5px;
          color: #8b95a3; white-space: nowrap; flex-shrink: 0; }
        .sl-card-review { display: flex; gap: 6px; align-items: center; margin: 8px 0 4px;
          flex-wrap: wrap; }
        .sl-status-select { font-size: 12px; background: #1b2735; color: #d0e4f7;
          border: 1px solid #2a3d55; border-radius: 5px; padding: 3px 8px; cursor: pointer; }
        .sl-status-select.sl-status-winner { border-color: #46a758; color: #46a758; }
        .sl-status-select.sl-status-test_candidate { border-color: #4a90d9; color: #4a90d9; }
        .sl-status-select.sl-status-rejected { border-color: #e5484d; color: #e5484d; }
        .sl-status-select.sl-status-researching { border-color: #f5a623; color: #f5a623; }
        .sl-notes-input { flex: 1; min-width: 140px; font-size: 12px; background: #1b2735;
          color: #d0e4f7; border: 1px solid #2a3d55; border-radius: 5px; padding: 3px 8px; }
        .sl-notes-save { background: none; border: 1px solid #2a3d55; color: #7fb2e8;
          font-size: 11.5px; padding: 3px 10px; border-radius: 5px; cursor: pointer; margin: 0; }
        .sl-notes-save:hover { background: #1b2735; }
        .sl-saved-note { margin: 0 0 6px; font-size: 12px; color: #8b95a3; font-style: italic; }
        .sl-card-footer { display: flex; justify-content: space-between; align-items: center;
          margin-top: 8px; border-top: 1px solid #1b2735; padding-top: 8px; }
        .pipeline { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 6px; }
        .pipeline-col { flex: 0 0 195px; min-width: 170px; }
        .pipeline-col-header { display: flex; justify-content: space-between; align-items: center;
          border-top: 3px solid; padding: 8px 0 6px; margin-bottom: 8px; }
        .pipeline-col-label { font-size: 11px; font-weight: 700; color: #c7d0db;
          text-transform: uppercase; letter-spacing: 0.06em; }
        .pipeline-col-count { font-size: 11px; font-weight: 700; padding: 1px 7px;
          border-radius: 999px; }
        .pipeline-card { background: #0e141b; border: 1px solid #232b36; border-radius: 8px;
          padding: 9px 10px; margin-bottom: 7px; cursor: pointer;
          transition: border-color 0.12s; }
        .pipeline-card:hover { border-color: #3a4d66; }
        .pipeline-card-name { font-size: 12px; font-weight: 600; line-height: 1.35;
          margin-bottom: 5px; overflow: hidden; display: -webkit-box;
          -webkit-line-clamp: 2; -webkit-box-orient: vertical; color: #d0dae8; }
        .pipeline-star { color: #f5c518; margin-right: 3px; font-size: 11px; }
        .pipeline-card-meta { display: flex; align-items: center; gap: 5px;
          margin-bottom: 5px; flex-wrap: wrap; }
        .pipeline-note { margin: 5px 0 0; font-size: 11px; color: #7d8896;
          font-style: italic; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .pipeline-more { font-size: 11.5px; color: #7d8896; text-align: center;
          padding: 4px 0; font-style: italic; margin: 0; }
        .pipeline-empty { font-size: 12px; color: #3a4555; text-align: center;
          padding: 10px 0; margin: 0; }
      `}</style>
    </main>
  );
}

function Stat({ label, value }) {
  return <div className="stat"><div className="v">{value}</div><div className="l">{label}</div></div>;
}

function Detail({ detail, onClose }) {
  if (detail.loading) {
    return <aside className="drawer"><button className="close" onClick={onClose}>×</button><p>Loading…</p></aside>;
  }
  const { product, scoring } = detail;
  const cats = scoring.categories || {};
  return (
    <aside className="drawer">
      <button className="close" onClick={onClose}>×</button>
      <h3>{product.name}</h3>
      <p className="sub">{product.category} · {product.country}</p>
      <div style={{ margin: "14px 0" }}>
        <Pill verdict={scoring.recommendation} />{" "}
        {scoring.score != null && <strong style={{ fontSize: 18 }}>{scoring.score}/60</strong>}{" "}
        <span className="muted">· confidence {scoring.confidence.level} ({scoring.confidence.supported}/{scoring.confidence.denominator})</span>
      </div>

      {scoring.eliminated ? (
        <div className="reason"><strong>Eliminated.</strong> {scoring.filter_reasons.join("; ")}</div>
      ) : (
        Object.entries(cats).map(([name, c]) => (
          <div className="catrow" key={name}>
            <span>{name.replace(/_/g, " ")}</span>
            <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="barwrap"><span className="bar" style={{ width: `${(c.display / 10) * 120}px` }} /></span>
              <span className="num" style={{ width: 42 }}>{c.display}/10</span>
            </span>
          </div>
        ))
      )}

      {scoring.net_profit_per_order != null && (
        <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
          Net profit / order: <strong>${scoring.net_profit_per_order}</strong> (CAC ${scoring.cac_used})
        </p>
      )}
      {scoring.cautions && scoring.cautions.length > 0 && (
        <div className="reason">⚠ {scoring.cautions.join("; ")}</div>
      )}
      <div className="reason">{scoring.recommendation_reason}</div>
    </aside>
  );
}
