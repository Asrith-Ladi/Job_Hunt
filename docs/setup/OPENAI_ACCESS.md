# OpenAI access setup

Use a project API key only on the private FastAPI server. Never paste the key into chat,
frontend code, source code, documentation, logs, or a committed environment file. The
React client receives only a configured/not-configured status and the model name.

## Recommended local setup

For the current PowerShell window:

```powershell
cd D:\Projects\job_hunt
$env:OPENAI_API_KEY = "replace-with-your-project-api-key"
$env:OPENAI_MODEL = "gpt-5.6-luna"
.\.venv\Scripts\python.exe -m uvicorn job_hunt.api.main:app --host 127.0.0.1 --port 8000
```

For Command Prompt:

```bat
cd /d D:\Projects\job_hunt
set OPENAI_API_KEY=replace-with-your-project-api-key
set OPENAI_MODEL=gpt-5.6-luna
.venv\Scripts\python.exe -m uvicorn job_hunt.api.main:app --host 127.0.0.1 --port 8000
```

Alternatively, copy `.env.example` to the Git-ignored `.env` file and replace only the
placeholder values. Environment variables have priority over `.env`. For an internet
deployment, use the host's encrypted secret manager instead of uploading `.env`.

The retired `.streamlit/secrets.toml` location is not read by the production application.
Use the process environment for deployment and the Git-ignored `.env` only for local use.

## Baseline resume

The private React job tool uploads an immutable Word `.docx` baseline to the app-owned Drive
Resume Library. A temporary validated server cache is stored below `JOB_HUNT_RUNTIME_DIR`
(`.secrets` locally); it is not the authoritative input. Generated documents are also
uploaded to the approved Drive application folder.

Persistent encrypted runtime storage is still required before deploying because the Google
token, OAuth state, research/plan cache, usage ledger mirror, and temporary resume cache must
survive or be safely reconstructed after restarts. The OpenAI key belongs in the host's
secret manager, not Drive or the runtime cache.

## Manual actions and cost boundary

Opening **Official JD + resume** does not call OpenAI. The first explicit action checks the
private research cache and calls Luna with web search only for a new/changed job or an
explicit refresh. Resume generation is a separate explicit action and has its own cache.
Normal Gmail, Company Portal, ATS, and Network runs remain LLM-free.

## Data sent to OpenAI

Official-job research sends only:

- normalized alert record ID;
- company;
- title;
- location;
- experience text;
- a validated public official-employer URL hint when already known.

Manual resume planning additionally sends only the contact-free text from Professional
Summary, Technical Skills, and Work Experience plus the selected public official-job
details and deterministic eligibility result. It never sends the DOCX itself, name, email,
phone, location/contact header, LinkedIn/GitHub profile links, Gmail bodies or identifiers,
alert-source URLs, or LinkedIn connection/contact data.

The generated DOCX is created locally from the private original. The model may propose a
supported summary and rank existing evidence IDs; server validation rejects unsupported
numeric or missing-skill claims, and the document editor only reorders existing skill and
work-bullet paragraphs. Every output is a draft that must be reviewed before use.
