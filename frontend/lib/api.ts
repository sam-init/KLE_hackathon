import { DocsResponse, Persona, ReviewResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

function normalizeErrorMessage(raw: string): string {
  const msg = raw.trim();
  const lower = msg.toLowerCase();

  if (lower.includes("http 429") || lower.includes("rate limit") || lower.includes("quota")) {
    return "NVIDIA model limit reached on Render. Please wait 1-2 minutes and retry, or use a smaller/faster model in backend env vars.";
  }

  if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
    return "Unable to reach backend API. Verify Render backend is awake and NEXT_PUBLIC_API_BASE_URL points to the correct .onrender.com URL.";
  }

  if (lower.includes("timed out") || lower.includes("timeout")) {
    return "Model request timed out on Render. Retry once, or switch to a faster model (for example qwen2.5-coder-7b) in backend env vars.";
  }

  if (lower.includes("internal server error")) {
    return "Backend failed while processing this request. Check Render logs for the matching request and retry.";
  }

  return msg || "Request failed";
}

/* ─── Response handler ─────────────────────────────────── */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `Request failed (HTTP ${res.status})`;
    try {
      const ct = res.headers.get("content-type") ?? "";
      if (ct.includes("application/json")) {
        const json = await res.json();
        message = json?.detail ?? json?.message ?? JSON.stringify(json);
      } else {
        const text = await res.text();
        if (text) message = text;
      }
    } catch {
      /* ignore parse errors */
    }
    throw new Error(normalizeErrorMessage(message));
  }
  return res.json() as Promise<T>;
}

/* ─── Job polling ──────────────────────────────────────── */
interface JobStatus {
  job_id: string;
  status: "queued" | "processing" | "done" | "error";
  message: string;
  result: unknown | null;
}

/**
 * Submit a job (POST) then poll GET /api/jobs/{job_id} until done.
 * No fixed timeout — keeps polling until the job finishes or errors.
 */
async function submitAndPoll<T>(
  submitFn: () => Promise<Response>,
  onProgress?: (msg: string) => void
): Promise<T> {
  const submitRes = await submitFn();
  const job: JobStatus = await handleResponse<JobStatus>(submitRes);

  if (job.status === "done" && job.result) {
    return job.result as T;
  }
  if (job.status === "error") {
    throw new Error(normalizeErrorMessage(job.message || "Job failed"));
  }

  // Poll until done
  const POLL_INTERVAL_MS = 3000;
  const job_id = job.job_id;

  while (true) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

    const pollRes = await fetch(`${API_BASE}/api/jobs/${job_id}`);
    const status: JobStatus = await handleResponse<JobStatus>(pollRes);

    if (onProgress) onProgress(status.message || status.status);

    if (status.status === "done" && status.result) {
      return status.result as T;
    }
    if (status.status === "error") {
      throw new Error(normalizeErrorMessage(status.message || "Job failed"));
    }
    // still "processing" or "queued" — keep polling
  }
}

/* ─── Review endpoints ─────────────────────────────────── */
export async function reviewFromRepo(
  repoUrl: string,
  persona: Persona,
  onProgress?: (msg: string) => void
): Promise<ReviewResponse> {
  return submitAndPoll<ReviewResponse>(
    () =>
      fetch(`${API_BASE}/api/review/repo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl, persona }),
      }),
    onProgress
  );
}

export async function reviewFromZip(
  file: File,
  persona: Persona,
  onProgress?: (msg: string) => void
): Promise<ReviewResponse> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("persona", persona);

  return submitAndPoll<ReviewResponse>(
    () => fetch(`${API_BASE}/api/review/upload`, { method: "POST", body: fd }),
    onProgress
  );
}

/* ─── Docs endpoints ───────────────────────────────────── */
export async function docsFromRepo(
  repoUrl: string,
  persona: Persona,
  encryptedDocsTokenOrProgress?: string | ((msg: string) => void),
  onProgress?: (msg: string) => void
): Promise<DocsResponse> {
  const encryptedDocsToken =
    typeof encryptedDocsTokenOrProgress === "string" ? encryptedDocsTokenOrProgress : undefined;
  const progressCb =
    typeof encryptedDocsTokenOrProgress === "function" ? encryptedDocsTokenOrProgress : onProgress;

  const payload: Record<string, string> = { repo_url: repoUrl, persona };
  if (encryptedDocsToken) payload.encrypted_docs_token = encryptedDocsToken;

  return submitAndPoll<DocsResponse>(
    () =>
      fetch(`${API_BASE}/api/docs/repo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    progressCb
  );
}

export async function docsFromZip(
  file: File,
  persona: Persona,
  onProgress?: (msg: string) => void
): Promise<DocsResponse> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("persona", persona);

  return submitAndPoll<DocsResponse>(
    () => fetch(`${API_BASE}/api/docs/upload`, { method: "POST", body: fd }),
    onProgress
  );
}

export interface VerifyDocsTokenResponse {
  valid: boolean;
  message?: string;
  encrypted_token?: string | null;
  repo_full_name?: string | null;
  default_branch?: string | null;
}

/**
 * Verify user-provided docs PAT and return an encrypted token if backend supports it.
 * If endpoint is unavailable, return a user-friendly response instead of throwing.
 */
export async function verifyDocsToken(
  repoUrl: string,
  patToken: string
): Promise<VerifyDocsTokenResponse> {
  const res = await fetch(`${API_BASE}/api/docs/verify-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      repo_url: repoUrl,
      pat_token: patToken,
    }),
  });

  if (res.status === 404 || res.status === 405) {
    return {
      valid: false,
      message:
        "Token verification endpoint is not available on this backend. Configure GITHUB_DOCS_TOKEN on the server for README push.",
      encrypted_token: null,
    };
  }

  return handleResponse<VerifyDocsTokenResponse>(res);
}
