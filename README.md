# Winning Products — Local MVP

A runnable local MVP that scores ecommerce/dropshipping products using **Scoring
Specification V2** (six categories, total /60), with elimination filters,
confidence levels, and honest data labeling. **No external APIs** — it scores the
real fields stored in a local SQLite database. Sample data is seeded so it works
on day one; real sources (Meta Ad Library, etc.) get connected later.

```
winning-products-mvp/
├─ backend/         FastAPI + SQLite (Python stdlib) + scoring engine
│  ├─ main.py       API endpoints
│  ├─ scoring.py    deterministic V2 scoring engine
│  ├─ db.py         SQLite layer
│  ├─ seed.py       inserts 20 sample products
│  └─ requirements.txt
└─ frontend/        Next.js dashboard (product list, scores, manual input form)
   ├─ pages/index.js
   ├─ package.json
   └─ next.config.js
```

## Prerequisites (install once)

- **Python 3.10+** — https://www.python.org/downloads/ (during install, tick **"Add python.exe to PATH"**)
- **Node.js 18+** — https://nodejs.org/ (LTS)

Check they're installed (open a new PowerShell window):

```powershell
python --version
node --version
```

---

## Run it on Windows

You need **two terminals** — one for the backend, one for the frontend.

### Terminal 1 — backend (API on http://localhost:8000)

```powershell
cd path\to\winning-products-mvp\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python seed.py
uvicorn main:app --reload --port 8000
```

You should see `Uvicorn running on http://127.0.0.1:8000`.
Leave this window open. (Interactive API docs: http://localhost:8000/docs)

> If `venv\Scripts\activate` is blocked by execution policy, run this once and retry:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
> Or skip the venv entirely and just run `pip install -r requirements.txt` then `python seed.py` and `uvicorn main:app --reload --port 8000`.

### Terminal 2 — frontend (dashboard on http://localhost:3000)

```powershell
cd path\to\winning-products-mvp\frontend
npm install
npm run dev
```

Then open **http://localhost:3000** in your browser.

---

## What you can do

- **Product list** — every seeded product with its score (/60), recommendation, country, category, net profit/order, and confidence.
- **Click any row** — opens a panel with the six category scores, the net-profit figure, any risk cautions, and the full reasoning for the verdict.
- **Add a product** — the manual-input form (right side). Fill what you have; leave the rest blank. Blank fields are treated as **Not Measured** — they lower confidence but never the score. On submit it's saved and scored immediately.

## The API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/products` | list with score + recommendation |
| GET | `/products/{id}` | full product + full scoring breakdown |
| POST | `/products/score` | score an existing product (`{"product_id": 1}`) or an inline product; optional `"cac"` |
| POST | `/discovery/manual` | manual product input — insert + score |
| GET | `/reports/daily` | aggregate summary (counts, average, top candidates) |

Example (PowerShell) — re-score product 1 with a custom CAC:

```powershell
curl.exe -X POST http://localhost:8000/products/score -H "Content-Type: application/json" -d "{\"product_id\":1,\"cac\":15}"
```

## Re-seeding

`python seed.py` wipes and rebuilds `products.db` with the 20 samples. Delete
`backend\products.db` anytime to start clean.

## Notes

- The seeded numbers are **illustrative sample values**, not live readings. They exist so the engine runs today.
- Net profit per order = `retail − supplier cost − shipping − CAC`. Default CAC is **$20**; change it per request via `/products/score`.
- Next step (later): replace the manual fields with live adapters (Meta Ad Library first). Because scoring reads stored fields only, connecting a source means filling those fields from the source — the scoring engine and schema don't change.
