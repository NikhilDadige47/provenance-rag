Follow this in order. Do not skip step 1. The full copy also lives in `DEPLOY.md`.

**What you get:** one public link like `https://something.onrender.com` (website + API together). **$0** if you pick Render **Free**, **no disk**, Turso, Qdrant free, Groq/Cohere trial. Not Heroku. Not Vercel.

---

### Step 1 — Put the new code on GitHub

Render builds from GitHub. Your Dockerfile and Turso code are **still only on this PC**.

Ask me to **commit** these files, then run:

```powershell
cd C:\PROVENANCE-RAG
git push origin main
```

On GitHub, confirm you can see `Dockerfile` and `src/storage/sql.py`. If they are missing, stop.

---

### Step 2 — Qdrant (search library)

1. Go to [https://cloud.qdrant.io](https://cloud.qdrant.io) and sign in.
2. Create a **free cluster**. Wait until it is running.
3. Copy the **URL** and **API key** into a notepad.
4. Collection name you will type later: `provenance_rag_v1` (the app creates it).

---

### Step 3 — Fill Qdrant from your laptop (once)

This loads the Apple demo PDFs. Needs Cohere.

```powershell
cd C:\PROVENANCE-RAG
$env:QDRANT_URL="https://PASTE-YOUR-QDRANT-URL"
$env:QDRANT_API_KEY="PASTE-YOUR-QDRANT-KEY"
$env:QDRANT_COLLECTION="provenance_rag_v1"
python scripts/ingest_demo.py --require-embeddings
```

Wait until it finishes with no error.

---

### Step 4 — Turso (you already have this)

From the Turso dashboard, copy:

- `TURSO_DATABASE_URL` (`libsql://....turso.io`)
- `TURSO_AUTH_TOKEN`

Local `.env` is only for your PC. You must paste these into **Render** in step 7.

---

### Step 5 — Render account

1. [https://dashboard.render.com](https://dashboard.render.com) — sign in with GitHub.
2. Plan: **Hobby** ($0). Not Pro.

---

### Step 6 — Create the web service

1. **New +** → **Web Service** → this GitHub repo.
2. Runtime: **Docker**. Branch: `main`. Dockerfile: `Dockerfile`.
3. Instance: **Free**.
4. **Do not add a disk. Do not pick Starter.**

---

### Step 7 — Environment variables

Add these in Render. Copy Cohere/Groq from local `.env`. Copy Qdrant and Turso from your notepad.

| Key | Value |
|---|---|
| `APP_ENV` | `production` |
| `TURSO_DATABASE_URL` | your `libsql://...` |
| `TURSO_AUTH_TOKEN` | your Turso token |
| `QDRANT_URL` | Qdrant URL |
| `QDRANT_API_KEY` | Qdrant key |
| `QDRANT_COLLECTION` | `provenance_rag_v1` |
| `COHERE_API_KEY` | from `.env` |
| `DEFAULT_LLM_PROVIDER` | `groq` |
| `DEFAULT_LLM_API_KEY` | from `.env` |
| `DEFAULT_LLM_MODEL` | from `.env` |

Do **not** set `DATA_DIR`. Do **not** commit `.env`.

Leave `FRONTEND_ORIGIN` until you have the live URL.

---

### Step 8 — Deploy

Click **Deploy**. First build takes **5–15 minutes**. Wait until it is **Live**.

Copy the URL: `https://YOUR-NAME.onrender.com`

---

### Step 9 — Cookies

Add:

| Key | Value |
|---|---|
| `FRONTEND_ORIGIN` | `https://YOUR-NAME.onrender.com` (no slash at the end) |
| `CORS_ORIGINS` | the same |

Save. Let it redeploy.

---

### Step 10 — Test

1. Open `https://YOUR-NAME.onrender.com/health` → `"ready": true`  
   After idle, the **first** open can take **about 1 minute**.
2. Open the homepage. Ask a demo question. You should see citations.

---

**$0 rules:** Hobby + Free, no disk, no Starter. Site sleeps after 15 minutes; quota stays in Turso. Do not ping it every 5 minutes (that uses up 750 free hours).

**Next action:** say **commit these files** so I can make the git commit. Then you `git push` and start at step 2.