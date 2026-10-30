# First deploy (Render Free, $0)

You will put one website on the internet. Visitors open one link. The API and the React app live on that same link. Cost is **$0** if you follow this exactly (Render Free, no disk, Turso, Qdrant free, Groq free, Cohere trial).

**You are not using Heroku or Vercel.**

At the end you will have: `https://something.onrender.com`

---

## 0. What you need open

1. This project on your computer (`C:\PROVENANCE-RAG`)
2. [GitHub](https://github.com) — repo `NikhilDadige47/provenance-rag`
3. [Render](https://dashboard.render.com) — sign in with GitHub
4. [Qdrant Cloud](https://cloud.qdrant.io)
5. [Turso](https://turso.tech) — you already created this
6. Your local `.env` (Cohere + Groq keys). **Never put `.env` on GitHub.**

Keep a notepad. You will copy URLs and keys into Render later.

---

## 1. Put the new code on GitHub

Render builds from GitHub, not from your desktop. Right now the Dockerfile and Turso code are **not** on GitHub until you commit and push.

In Cursor, ask the agent to **commit**, then in PowerShell:

```powershell
cd C:\PROVENANCE-RAG
git push origin main
```

Refresh GitHub in the browser. You should see `Dockerfile`, `render.yaml`, and `src/storage/sql.py`.

If those files are missing on GitHub, stop. Render will deploy the old app.

---

## 2. Qdrant Cloud (search index)

This stores the demo document vectors. Free cluster is enough.

1. Open [https://cloud.qdrant.io](https://cloud.qdrant.io) and sign up / log in.
2. Create a **cluster**. Wait until it is running.
3. Copy:
   - **Cluster URL** (starts with `https://`)
   - **API key**
4. Collection name to use later: `provenance_rag_v1`  
   You do **not** create the collection by hand.

---

## 3. Load the Apple demo PDFs into Qdrant (on your PC)

Do this once from your laptop. It uses your Cohere key.

PowerShell, from the project folder. Paste **your** Qdrant URL and key:

```powershell
cd C:\PROVENANCE-RAG
$env:QDRANT_URL="https://PASTE-QDRANT-URL"
$env:QDRANT_API_KEY="PASTE-QDRANT-KEY"
$env:QDRANT_COLLECTION="provenance_rag_v1"
python scripts/ingest_demo.py --require-embeddings
```

Wait until it finishes without an error. This can take several minutes.

If Cohere is missing or trial calls are exhausted, ingest fails and the live demo will have no answers.

---

## 4. Turso (sessions + 15-question quota)

This replaces a Render disk. Free.

1. Open [https://turso.tech](https://turso.tech) and sign in.
2. Create a database if you do not have one.
3. Copy:
   - **Database URL** (`libsql://....turso.io`)
   - **Auth token**

You can keep these in local `.env` for your PC. You must **also** paste them into Render in step 7. Local `.env` is not sent to Render.

---

## 5. Render account = Hobby ($0)

1. Open [https://dashboard.render.com](https://dashboard.render.com).
2. If it asks for a plan, choose **Hobby** — **$0/mo plus compute**.
3. Do **not** choose Pro.

Hobby is the account. It is not the website yet.

---

## 6. Create the website (Free instance, no disk)

1. **New +** → **Web Service**.
2. Connect GitHub if asked. Select **`provenance-rag`**.
3. Fill in:

| Field | Value |
|---|---|
| Name | `provenance-rag` (any name is fine) |
| Language / runtime | **Docker** |
| Branch | `main` |
| Dockerfile path | `Dockerfile` |
| Instance type | **Free** |

4. **Do not** add a disk.  
5. **Do not** pick Starter ($7).

---

## 7. Environment variables (the important list)

In the same service, open **Environment**. Add every row. Copy Cohere and Groq from your local `.env`. Copy Qdrant from step 2. Copy Turso from step 4.

Mark keys as secret if Render shows that checkbox.

| Key | Value |
|---|---|
| `APP_ENV` | `production` |
| `TURSO_DATABASE_URL` | `libsql://....turso.io` |
| `TURSO_AUTH_TOKEN` | your Turso token |
| `QDRANT_URL` | Qdrant cluster URL |
| `QDRANT_API_KEY` | Qdrant key |
| `QDRANT_COLLECTION` | `provenance_rag_v1` |
| `COHERE_API_KEY` | from local `.env` |
| `DEFAULT_LLM_PROVIDER` | `groq` |
| `DEFAULT_LLM_API_KEY` | from local `.env` |
| `DEFAULT_LLM_MODEL` | from local `.env` (example `openai/gpt-oss-120b`) |
| `FRONTEND_ORIGIN` | leave for step 9 |
| `CORS_ORIGINS` | leave for step 9 |

**Do not set** `DATA_DIR`.  
**Do not** paste `.env` into git.

Optional (only if you already use them locally): `LANDINGAI_API_KEY`, `LLAMAPARSE_API_KEY`, Langfuse keys.

---

## 8. Deploy and wait

1. Click **Deploy** / **Create Web Service**.
2. Watch **Logs**. The first build installs Node, builds the React app, then Python. **5–15 minutes** is normal.
3. Success: status **Live**, log line like `Provenance RAG API starting up`.
4. Render shows a URL: `https://something.onrender.com`

If the build cannot find `Dockerfile`, go back to step 1 (code not on GitHub).

---

## 9. Tell the app its public URL

1. Copy the `https://....onrender.com` URL (no slash at the end).
2. Environment → add:

| Key | Value |
|---|---|
| `FRONTEND_ORIGIN` | that exact `https://....onrender.com` URL |
| `CORS_ORIGINS` | the same URL |

3. Save. Render redeploys once. That makes cookies work on HTTPS.

---

## 10. Check that it works

1. Open `https://YOUR-SERVICE.onrender.com/health`  
   You want `"ready": true`. First load after idle can take **about one minute** (Free sleeps).
2. Open `https://YOUR-SERVICE.onrender.com`  
   Ask a demo question (Tier A). You should get an answer with citations.
3. Optional: upload a small PDF (Tier B).

From your PC:

```powershell
python scripts/smoke_prod.py https://YOUR-SERVICE.onrender.com
```

You want `tier_a pass`. `tier_c skip` is fine.

---

## 11. How this $0 setup behaves

- **Sleep:** after 15 minutes with no visitors, Render spins down. The next person waits ~1 minute.
- **Quota:** stored in Turso, so the 15-question cap **does not** reset just because the site slept.
- **Qdrant free:** if nobody uses it for a week, the cluster can suspend. Open the live site or the Qdrant dashboard about once a week.
- **Do not** add an uptime ping every 5 minutes. That burns the **750 free hours** and can stop the app until next month.

---

## If something fails

| What you see | What to do |
|---|---|
| No `Dockerfile` in the build | Commit + `git push origin main` |
| `/health` 503 or `qdrant` error | Wrong `QDRANT_URL` / `QDRANT_API_KEY`, or cluster suspended |
| Demo answers empty / not found | Step 3 ingest did not finish, or collection name is not `provenance_rag_v1` |
| Cookies / session weird on HTTPS | `FRONTEND_ORIGIN` is not the exact live URL |
| App talks to a local `.db` on Render | `TURSO_DATABASE_URL` missing **on Render** (local `.env` is not enough) |
| Deploy is charging $7 | You picked **Starter**. Switch instance to **Free** |

---

## Later (optional, not $0)

If a recruiter must not wait a minute: same service → instance **Starter** + optional 1 GB disk at `/data` ≈ **$7.25/month**. You can keep Turso either way. No Vercel. No Heroku.
