# Provenance RAG — Upload terms and privacy

By uploading a document you confirm:

1. **Right to upload.** You have the right to submit this file. Do not upload other people’s confidential documents without permission.
2. **Where text goes.** Parsed text is sent to the parser you selected (Landing AI, LlamaParse, or local PyMuPDF), then to Cohere for embeddings/rerank, and to the active LLM (the owner’s Groq key, or your own key if you pasted one).
3. **Retention.** This is an isolated browser session. Vectors, SQL rows, and cached parses are wiped when the session TTL expires, when you close the tab, or when you click delete. Default TTL is two hours.
4. **Keys.** Visitor parser and LLM keys transit this server in memory for that request or job only. They are never written to disk, logs, traces, or the database. Using a key here requires trust in the host.
5. **Free demo caps.** Owner-funded questions, documents, pages, and daily IP limits apply. When those caps hit, paste your own LLM key or wait for the daily reset.

The demo corpus (Apple 10-K filings) is read-only shared data. Your uploads never join that corpus.
