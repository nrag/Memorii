/**
 * Typed client for the Memorii loopback runtime sidecar (protocol v1).
 *
 * Speaks the same closed request/response contract as the embedded path
 * and the Python client: loopback-only binding (remote binding is
 * disabled server-side and refused here client-side), installation-issued
 * bearer credentials, and the sidecar's closed error codes surfaced on
 * {@link RuntimeClientError}. Credentials never appear in URLs or logs.
 */

export type RecommendationKind =
  | "test"
  | "inspect"
  | "ask"
  | "revalidate"
  | "reconcile"
  | "wait"
  | "none";

export type EnvelopeStatus =
  | "ready"
  | "revalidation_required"
  | "reconcile_required"
  | "pending"
  | "unavailable";

export type RuntimeView =
  | "execution"
  | "solver"
  | "summary"
  | "history"
  | "neighborhood";

/** Closed error codes from the sidecar's error envelope. */
export type RuntimeErrorCode =
  | "unauthenticated"
  | "denied"
  | "not_found"
  | "unsupported_version"
  | "unsupported_configuration"
  | "invalid_request"
  | "conflict"
  | "stale_cursor"
  | "resource_exhausted"
  | "unavailable"
  | "integrity_error"
  | "needs_reconciliation";

export interface HarnessOutputBlock {
  kind: "work" | "frontier" | "evidence" | "blocker";
  label: string;
  candidate: boolean;
  committed: boolean;
  detail?: string | null;
}

export interface HarnessStateEnvelope {
  protocol_version: 1;
  task_id: string;
  revision: number;
  checkpoint_ref?: string | null;
  status: EnvelopeStatus;
  goal?: string | null;
  current_execution_node?: string | null;
  execution_status?: string | null;
  ready_work: HarnessOutputBlock[];
  blocked_work: HarnessOutputBlock[];
  constraints: string[];
  remaining_acceptance: string[];
  solver_id?: string | null;
  solver_category?: string | null;
  candidate_hypotheses: HarnessOutputBlock[];
  committed_hypotheses: HarnessOutputBlock[];
  selected_overlay_id?: string | null;
  frontier: HarnessOutputBlock[];
  unresolved_questions: string[];
  unexplained_evidence: HarnessOutputBlock[];
  reopenable_branches: HarnessOutputBlock[];
  recommendation_kind: RecommendationKind;
  recommendation_target?: string | null;
  recommendation_evidence: string[];
  recommendation_revision?: number | null;
  pending_actions: string[];
  source_refs: string[];
  freshness_note?: string | null;
  omissions: string[];
  state_digest: string;
  continuation_cursor?: string | null;
}

export class RuntimeClientError extends Error {
  readonly code: RuntimeErrorCode;
  readonly httpStatus: number;
  readonly detail?: string | null;

  constructor(code: RuntimeErrorCode, httpStatus: number, detail?: string | null) {
    super(`${httpStatus} ${code}${detail ? `: ${detail}` : ""}`);
    this.name = "RuntimeClientError";
    this.code = code;
    this.httpStatus = httpStatus;
    this.detail = detail ?? null;
  }
}

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

export interface RuntimeStateClientOptions {
  /** Loopback base URL of the sidecar, e.g. http://127.0.0.1:8734 */
  baseUrl: string;
  /** Installation-issued bearer credential; never logged or put in URLs. */
  credential: string;
  timeoutMs?: number;
}

export class RuntimeStateClient {
  private readonly baseUrl: string;
  private readonly credential: string;
  private readonly timeoutMs: number;

  constructor(options: RuntimeStateClientOptions) {
    const parsed = new URL(options.baseUrl);
    // Node keeps the brackets on IPv6 hostnames ([::1]); strip them.
    const hostname = parsed.hostname.replace(/^\[|\]$/g, "");
    if (parsed.protocol !== "http:" || !LOOPBACK_HOSTS.has(hostname)) {
      // Remote binding is disabled by the sidecar; refuse client-side.
      throw new Error("runtime client only binds loopback sidecar URLs");
    }
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.credential = options.credential;
    this.timeoutMs = options.timeoutMs ?? 10_000;
  }

  async getState(
    taskId: string,
    options: { view?: RuntimeView; cursor?: string } = {},
  ): Promise<HarnessStateEnvelope> {
    const body = JSON.stringify({
      protocol_version: 1,
      task_id: taskId,
      view: options.view ?? "summary",
      ...(options.cursor !== undefined ? { cursor: options.cursor } : {}),
    });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}/v1/runtime/state`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${this.credential}`,
        },
        body,
        signal: controller.signal,
      });
    } catch (cause) {
      throw new RuntimeClientError("unavailable", 0, String(cause));
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) {
      let code: RuntimeErrorCode = "unavailable";
      let detail: string | null = null;
      try {
        const parsed = (await response.json()) as Record<string, unknown>;
        if (typeof parsed["code"] === "string") {
          code = parsed["code"] as RuntimeErrorCode;
        }
        if (typeof parsed["detail"] === "string") {
          detail = parsed["detail"];
        }
      } catch {
        // non-JSON or non-object error body maps to unavailable
      }
      throw new RuntimeClientError(code, response.status, detail);
    }
    return (await response.json()) as HarnessStateEnvelope;
  }
}
