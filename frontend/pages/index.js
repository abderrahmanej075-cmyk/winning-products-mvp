import { useEffect, useState } from "react";

const API = "http://localhost:8000";

const VERDICT_COLOR = {
  "Reject": "#e5484d",
  "Watchlist": "#f5a623",
  "Test with small budget": "#4a90d9",
  "Strong candidate": "#46a758",
};

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

      <div className="grid">
        <section className="panel">
          <h2>Products</h2>
          <table>
            <thead>
              <tr>
                <th>Product</th><th>Category</th><th>Country</th>
                <th className="num">Score</th><th>Recommendation</th>
                <th className="num">Net/order</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
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
