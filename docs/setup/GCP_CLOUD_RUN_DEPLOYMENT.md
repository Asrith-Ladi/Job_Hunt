# Personal GCP Cloud Run deployment runbook

Last reviewed: 2026-09-01
Audience: project owner and future implementation agents
Status: reference prepared; deployment execution is not yet approved or implemented

This is the durable reference for deploying the personal React/FastAPI Job Hunt application
without depending on the owner's laptop. It intentionally covers a private, single-user
deployment. Do not reinterpret it as approval for scheduling, public access, or multi-user
accounts.

## Current decision

- Runtime: Google Cloud Run in `asia-south1` (Mumbai).
- Access control: Identity-Aware Proxy (IAP), restricted to the owner's Google account.
- Application OAuth: the existing Web OAuth client with only `gmail.readonly` and `drive.file`.
- Static secrets: Google Secret Manager.
- Mutable private runtime files: one private Cloud Storage bucket mounted at `/data`.
- Durable user artifacts and source-of-truth files: the app-owned `Job Hunt` Google Drive tree.
- Scaling: zero minimum instances, one maximum instance, request concurrency high enough for
  progress polling.
- Scheduling: deferred until several deployed manual runs succeed.

Cloud Storage FUSE does not provide concurrent-write locking or complete POSIX semantics.
Limiting the personal service to one instance makes it an acceptable migration bridge. Replace
file-based mutable state with a tenant-aware database before a multi-user release.

## Architecture

```text
Owner browser
    |
    v
Cloud Run IAP (only approved Google account)
    |
    v
React static build + FastAPI in one Cloud Run container
    |                  |                    |
    v                  v                    v
Secret Manager    Private /data mount   Google OAuth APIs
(API/client keys) (token and cache)      (Gmail read-only + Drive app files)
                                              |
                                              v
                                     Job Hunt Drive workspace
```

## Responsibility split

### The owner performs

- select the Google Cloud project and link billing;
- enable APIs;
- create the runtime service account and private bucket;
- create secrets without sharing their values;
- configure the OAuth audience, callback, and IAP access;
- approve the final deployment and complete browser consent.

### Codex implements and verifies

- the production Docker image and `.dockerignore`;
- Cloud Run `$PORT` startup behavior;
- production runtime path validation;
- deployment/rollback commands and tests;
- local container verification and a deployment PR;
- the post-deployment smoke-test checklist.

## Gate: do not deploy the current repository yet

The deployment command in this document is a reviewed template, not a command to run against the
current `main` branch. Before the first deployment, the repository must contain and verify:

- a multi-stage `Dockerfile` that builds React and installs the Python package;
- a `.dockerignore` that excludes credentials, private inputs, `.secrets`, outputs, and local
  environments;
- a container command that listens on `0.0.0.0:$PORT`;
- startup validation for required secret paths and writable runtime paths;
- container-level health and smoke tests.

## Phase 1 - prepare Google Cloud

Prefer the existing Google Cloud project that owns the current `oauth-client.json`. Creating a
different project requires a new OAuth client and a fresh Google authorization.

### 1. Select the project and billing account

1. Open <https://console.cloud.google.com/>.
2. Select the existing OAuth project.
3. Link a billing account under **Billing**.
4. Record the immutable project ID, not only the display name.
5. Create a small budget alert. A budget alert warns about spend; it is not a hard spending cap.

Set reusable values in Google Cloud Shell:

```bash
export JOB_HUNT_PROJECT_ID="replace-with-project-id"
export JOB_HUNT_REGION="asia-south1"
export JOB_HUNT_SERVICE="job-hunt"
export JOB_HUNT_RUNTIME_SA="job-hunt-runtime@${JOB_HUNT_PROJECT_ID}.iam.gserviceaccount.com"
export JOB_HUNT_BUCKET="${JOB_HUNT_PROJECT_ID}-job-hunt-private"

gcloud config set project "${JOB_HUNT_PROJECT_ID}"
```

Bucket names are globally unique. If the proposed value is already taken, add a private random
suffix and preserve the final name for the deployment command.

### 2. Enable required APIs

Run in Google Cloud Shell:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  iap.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  gmail.googleapis.com \
  drive.googleapis.com
```

Google Sheets API is not required by the active application. It is needed only by historical
tracker utilities.

### 3. Create the runtime service account

```bash
gcloud iam service-accounts create job-hunt-runtime \
  --display-name="Job Hunt Cloud Run Runtime"
```

Do not give this account Owner or Editor. Bucket and secret permissions are granted narrowly in
the following steps.

### 4. Create the private runtime bucket

Console method:

1. Open **Cloud Storage -> Buckets -> Create**.
2. Use the value recorded in `JOB_HUNT_BUCKET`.
3. Select region `asia-south1` and storage class **Standard**.
4. Enable **Uniform bucket-level access**.
5. Enable **Public access prevention**.
6. Create the bucket.
7. Open **Permissions -> Grant access**.
8. Add `job-hunt-runtime@PROJECT_ID.iam.gserviceaccount.com`.
9. Grant **Storage Object User** (`roles/storage.objectUser`).

Equivalent Cloud Shell commands:

```bash
gcloud storage buckets create "gs://${JOB_HUNT_BUCKET}" \
  --location="${JOB_HUNT_REGION}" \
  --uniform-bucket-level-access \
  --public-access-prevention

gcloud storage buckets add-iam-policy-binding "gs://${JOB_HUNT_BUCKET}" \
  --member="serviceAccount:${JOB_HUNT_RUNTIME_SA}" \
  --role="roles/storage.objectUser"
```

Never make this bucket public. It contains the Google refresh token and private runtime state.

### 5. Create secrets

Use **Security -> Secret Manager -> Create secret** so values do not enter shell history.

| Secret | Stored value | Cloud Run exposure |
|---|---|---|
| `job-hunt-openai-api-key` | OpenAI project API key | `OPENAI_API_KEY` environment secret |
| `job-hunt-session-secret` | New random 48-byte-or-longer value | `JOB_HUNT_SESSION_SECRET` environment secret |
| `job-hunt-google-oauth-client` | Complete existing `oauth-client.json` contents | `/secrets/oauth-client.json` mounted secret file |

Generate a session secret locally in PowerShell:

```powershell
[Convert]::ToBase64String(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
)
```

For every secret, grant the runtime service account **Secret Manager Secret Accessor**. The
values must never be pasted into chat, committed, embedded in the image, or placed in deployment
documentation.

After the three secrets exist, permission bindings can be added without exposing their values:

```bash
for SECRET in \
  job-hunt-openai-api-key \
  job-hunt-session-secret \
  job-hunt-google-oauth-client
do
  gcloud secrets add-iam-policy-binding "${SECRET}" \
    --member="serviceAccount:${JOB_HUNT_RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

### 6. Configure the application OAuth audience

1. Open **Google Auth Platform -> Audience**.
2. Keep the audience **External** for a personal Gmail account.
3. Keep the owner as the only intended user.
4. For daily refresh-token persistence, change publishing status from **Testing** to
   **In production**.
5. Expect an unverified-app warning and a 100-user cap while the personal app remains unverified.
6. Under **Data access**, confirm only:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/drive.file`
7. Keep the existing client type **Web application**.

Testing-mode authorizations involving these scopes expire after seven days. Google currently
allows personal-use apps with fewer than 100 known users to continue without completing OAuth
verification, although warning and cap behavior still applies. Re-evaluate verification before
adding outside users.

## Phase 2 - deployment implementation PR

Before running Phase 3, the implementation PR must include:

- [ ] production `Dockerfile`;
- [ ] `.dockerignore` private-data exclusions;
- [ ] `$PORT` and `0.0.0.0` server binding;
- [ ] `/app/frontend/dist` included and served by FastAPI;
- [ ] `/data/runtime` and `/data/outputs` created or validated at startup;
- [ ] `/secrets/oauth-client.json` read-only credential handling;
- [ ] local Docker build and `/api/health` verification;
- [ ] backend tests, Ruff, strict TypeScript, and production frontend build;
- [ ] deployment configuration documented without secret values;
- [ ] rollback command verified against the chosen service name and region.

## Phase 3 - first private deployment

Run only after Phase 2 is merged. Start from a clean clone or the synchronized `main` branch.

### 7. Deploy the private Cloud Run service

From the repository root in Cloud Shell:

```bash
gcloud run deploy "${JOB_HUNT_SERVICE}" \
  --source=. \
  --region="${JOB_HUNT_REGION}" \
  --service-account="${JOB_HUNT_RUNTIME_SA}" \
  --execution-environment=gen2 \
  --no-allow-unauthenticated \
  --cpu=1 \
  --memory=1Gi \
  --min-instances=0 \
  --max-instances=1 \
  --concurrency=10 \
  --timeout=900 \
  --add-volume="mount-path=/data,type=cloud-storage,bucket=${JOB_HUNT_BUCKET},readonly=false" \
  --set-env-vars="JOB_HUNT_PROJECT_ROOT=/app,JOB_HUNT_RUNTIME_DIR=/data/runtime,JOB_HUNT_OUTPUT_DIR=/data/outputs,JOB_HUNT_GMAIL_RUN_DIR=/data/outputs/gmail_runs,JOB_HUNT_REGISTRY_PATH=/data/runtime/source_cache/Company_Source_Registry.xlsx,JOB_HUNT_GOOGLE_CREDENTIALS=/secrets/oauth-client.json,JOB_HUNT_COOKIE_SECURE=true,OPENAI_MODEL=gpt-5.6-luna" \
  --update-secrets="/secrets/oauth-client.json=job-hunt-google-oauth-client:latest,OPENAI_API_KEY=job-hunt-openai-api-key:latest,JOB_HUNT_SESSION_SECRET=job-hunt-session-secret:latest"
```

Cloud Run's default request timeout is five minutes. This template uses 15 minutes because a
bounded Gmail or portal request can exceed five minutes. Do not raise it above 15 minutes until
long work is moved into a resumable background job.

Capture the generated service URL:

```bash
export JOB_HUNT_URL="$(
  gcloud run services describe "${JOB_HUNT_SERVICE}" \
    --region="${JOB_HUNT_REGION}" \
    --format='value(status.url)'
)"

printf '%s\n' "${JOB_HUNT_URL}"
```

### 8. Enable IAP for the owner

For a personal project without a Google organization, perform the first IAP setup in the Cloud
Console:

1. Open **Cloud Run -> job-hunt -> Security**.
2. Select **Require authentication -> Identity-Aware Proxy (IAP)**.
3. Select **Configure in IAP** if prompted.
4. Use an **External** audience.
5. Select **Auto generate credentials** for the initial IAP client.
6. Return to the Cloud Run service's IAP policy.
7. Add the owner's Gmail address.
8. Grant **IAP-secured Web App User** (`roles/iap.httpsResourceAccessor`).
9. Save and verify the service reports `IAP Enabled: true`.

The IAP client protects entry to the website. It is separate from the application's Web OAuth
client that grants Gmail and Drive access.

### 9. Configure the deployed application URL

Update Cloud Run with its stable HTTPS URL:

```bash
gcloud run services update "${JOB_HUNT_SERVICE}" \
  --region="${JOB_HUNT_REGION}" \
  --update-env-vars="JOB_HUNT_FRONTEND_URL=${JOB_HUNT_URL},JOB_HUNT_OAUTH_REDIRECT_URI=${JOB_HUNT_URL}/api/auth/google/callback,JOB_HUNT_CORS_ORIGINS=${JOB_HUNT_URL}"
```

Then open **Google Auth Platform -> Clients -> existing Web application client** and add this
exact authorized redirect URI:

```text
https://SERVICE-URL/api/auth/google/callback
```

Use the actual value of `JOB_HUNT_URL`. Scheme, host, path, case, and trailing slash behavior
must match exactly. Keep the local callback as a second authorized URI if local development must
continue:

```text
http://localhost:8000/api/auth/google/callback
```

### 10. Connect Google in production

1. Open the Cloud Run URL in a normal browser.
2. Sign through IAP with the approved owner account.
3. Select **Connect Google** in Job Hunt.
4. Review and approve only Gmail read-only and Drive app-file access.
5. Return to Job Hunt and confirm **Google connected**.
6. Do not copy the generated token out of the private bucket.

## Phase 4 - deployment acceptance

Run the following bounded checks in order:

- [ ] An approved browser can load the application.
- [ ] An unapproved/incognito Google account is rejected by IAP.
- [ ] `/api/health` reports `{"status":"ok"}` after authentication.
- [ ] Google OAuth returns to the HTTPS application without `redirect_uri_mismatch`.
- [ ] A one-day Gmail search reads only the approved LinkedIn/Naukri labels.
- [ ] One Company Portal search completes and remains temporary.
- [ ] One ATS search completes and remains temporary.
- [ ] Saving one result makes it appear in Applications after a browser refresh.
- [ ] One official-JD action shows source and completeness status.
- [ ] One generated document appears in the expected Drive resume folder.
- [ ] One manually applied job archives readable DOCX/Markdown plus structured JSON in Drive.
- [ ] A new Cloud Run revision starts with Google still connected.
- [ ] Cloud Logging contains no OAuth tokens, API keys, Gmail bodies, resumes, or connection data.
- [ ] AI usage appears only for an explicit per-job intelligence action.

After these pass, keep runs manual for several days. Scheduling is a separate approved task only
after repeated stable runs.

## Cost controls

- Keep minimum instances at `0` and maximum instances at `1`.
- Use request-based billing and avoid an uptime-monitor keep-alive ping.
- Create billing budget alerts before the first deployment.
- Keep search batches bounded; OpenAI cost remains separate from Cloud Run cost.
- Review Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Storage, and network usage.
- The Cloud Run free tier can cover small personal workloads but does not guarantee a zero bill.

## Rollback

List revisions:

```bash
gcloud run revisions list \
  --service="${JOB_HUNT_SERVICE}" \
  --region="${JOB_HUNT_REGION}"
```

Route all traffic back to a known-good revision:

```bash
gcloud run services update-traffic "${JOB_HUNT_SERVICE}" \
  --region="${JOB_HUNT_REGION}" \
  --to-revisions="KNOWN_GOOD_REVISION=100"
```

Rollback changes traffic only. Do not delete the bucket, secrets, OAuth client, Drive workspace,
or old revision during incident recovery.

## Disconnect and token recovery

If the Google token is suspected to be exposed:

1. Revoke the Job Hunt application's access from the owner's Google Account security page.
2. Stop traffic to the Cloud Run service or remove the owner's IAP access temporarily.
3. Delete only the exact `google_token.json` object below the mounted runtime directory.
4. Rotate the OAuth client secret if the client JSON was exposed.
5. Rotate the OpenAI and session secrets if either was exposed.
6. Redeploy and explicitly reconnect Google.

Do not delete the whole bucket as a token-recovery shortcut; it can contain other private state.

## Troubleshooting

| Symptom | Likely cause | Check or fix |
|---|---|---|
| `redirect_uri_mismatch` | Cloud Run environment and OAuth client URI differ | Compare the full HTTPS callback character-for-character |
| IAP `403` | Owner lacks IAP Web App User | Review the service IAP policy and exact Gmail principal |
| Container does not start | Server is not listening on Cloud Run `$PORT` | Confirm `0.0.0.0:$PORT` and inspect revision logs |
| Google disconnects after a revision or scale-down | Token wrote to ephemeral storage or bucket mount failed | Check `/data/runtime`, volume configuration, and Storage Object User role |
| Secret cannot be read | Runtime service account lacks secret access | Grant Secret Manager Secret Accessor on the exact secret |
| Search returns `504` | Request exceeded Cloud Run timeout | Confirm 900-second timeout, then reduce the batch; do not hide an unbounded operation with a larger timeout |
| Live progress disappears | Requests reached different instances | Confirm maximum instances is `1` during the personal file-backed phase |
| Registry refresh falls back | Drive registry is unavailable or invalid | Inspect UI warning; repair the authoritative Drive workbook rather than overwriting it from cache |
| Resume/JD output missing | Drive upload failed or Google token expired | Check the action error and Drive folder before retrying |

## Information safe to share with Codex

Safe:

- GCP project ID;
- Cloud Run region;
- bucket name;
- service name;
- deployed `run.app` URL;
- non-secret error messages with tokens removed.

Never share:

- OAuth client JSON contents;
- Google refresh/access tokens;
- OpenAI API key;
- session secret;
- raw Gmail content, resumes, or private LinkedIn exports unless explicitly needed and approved.

## Official references

- [Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Deploy Cloud Run services](https://docs.cloud.google.com/run/docs/deploying)
- [Configure IAP directly on Cloud Run](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
- [Configure Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Configure Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [Configure Cloud Run request timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Google OAuth Web Server flow](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google OAuth token expiration](https://developers.google.com/identity/protocols/oauth2)
- [OAuth personal-use verification exemption](https://support.google.com/cloud/answer/13464323)
