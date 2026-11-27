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
  task_version?: number | null;
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

/** Closed v1 runtime command union, validated server-side. */
export type RuntimeCommandKind =
  | "start_task"
  | "resume_task"
  | "record_observation"
  | "propose_state_change"
  | "record_action_dispatch"
  | "record_action_result"
  | "checkpoint_task"
  | "replan_task"
  | "complete_task"
  | "pause_task"
  | "abort_task";

export interface RuntimeCommand {
  protocol_version?: 1;
  kind: RuntimeCommandKind;
  operation_id: string;
  task_id?: string | null;
  expected_revision?: number | null;
  goal?: string | null;
  completion_evidence?: unknown | null;
  pause_reason?: string | null;
  abort_reason?: string | null;
  proposal?: unknown | null;
  /** Required for record_observation (64 hex chars); rejected elsewhere. */
  source_digest?: string;
}

export interface OperationOrigin {
  coordinate: {
    installation_id: string;
    repository_id: string;
    generation_id: string;
    principal: string;
    client_namespace: string;
    operation_id: string;
    request_digest: string;
  };
  signature: string;
}

export interface ConsolidationReadRequest {
  protocol_version?: 1;
  task_id: string;
  origin_operation_id: string;
  host_binding?: { installation_id: string; client_namespace: string; task_id: string } | null;
  cursor?: string | null;
  page_size?: number;
}

export interface WritebackDecisionRequest {
  protocol_version?: 1;
  host_binding: { installation_id: string; client_namespace: string; task_id: string };
  task_id: string;
  result_id: string;
  output_id: string;
  expected_offer_version: number;
  expected_payload_digest: string;
  operation_id: string;
  decision: "accept" | "decline";
}

type WritebackDeliveryStatus = "pending" | "delivering" | "delivered" | "rejected" | "needs_reconciliation";

export interface WritebackDecisionReceipt {
  decision_id: string;
  outcome: "accepted" | "declined";
  offer_version: 2;
  delivery_id: string | null;
  delivery_status: WritebackDeliveryStatus | null;
}

export interface ConsolidationSourceReference {
  source_id: string;
  source_digest: string;
}

interface DerivedCandidate {
  source_refs: ConsolidationSourceReference[];
  solver_run_id?: string | null;
  execution_node_id?: string | null;
  provenance: "derived";
}

export type ConsolidationPayload =
  | (DerivedCandidate & { kind: "episodic_summary"; summary: string })
  | (DerivedCandidate & { kind: "skill_candidate"; title: string; summary: string; steps: string[] })
  | (DerivedCandidate & { kind: "semantic_candidate"; abstraction: string })
  | (DerivedCandidate & { kind: "user_candidate"; preference: string; valid_from?: string | null; valid_to?: string | null })
  | { kind: "unresolved_follow_up_summary"; truncated: boolean; items: {
    node_id: string; reason: string; source_refs: ConsolidationSourceReference[];
  }[] }
  | { kind: "archive_package"; reference: {
    installation_id: string; partition_id: string; task_id: string; origin_revision: number;
    checkpoint_id: string; checkpoint_digest: string; manifest_id: string; manifest_digest: string;
  } };

export interface ConsolidationReadPage {
  protocol_version: 1;
  result_id: string;
  origin_revision: number;
  outputs: {
    output: { output_id: string; ordinal: number; payload_digest: string; payload: ConsolidationPayload };
    offer: {
      output_id: string; offer_version: number; payload_digest: string;
      decision_status: "offered" | "accepted" | "declined";
      delivery_status: WritebackDeliveryStatus | null;
    } | null;
  }[];
  omissions: {
    kind: "episodic_summary" | "skill_candidate" | "semantic_candidate" | "user_candidate";
    reason: "insufficient_evidence" | "policy_denied";
  }[];
  continuation_cursor?: string | null;
}

export interface SpoolRecord {
  operation_id: string;
  producer_binding: string;
  request_digest: string;
  state: "pending" | "committed" | "dead_letter";
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
    let end = options.baseUrl.length;
    while (options.baseUrl[end - 1] === "/") {
      end -= 1;
    }
    this.baseUrl = options.baseUrl.slice(0, end);
    this.credential = options.credential;
    this.timeoutMs = options.timeoutMs ?? 10_000;
  }

  async getState(
    taskId: string,
    options: { view?: RuntimeView; cursor?: string; includeTaskVersion?: boolean } = {},
  ): Promise<HarnessStateEnvelope> {
    const body = JSON.stringify({
      protocol_version: 1,
      task_id: taskId,
      view: options.view ?? "summary",
      ...(options.cursor !== undefined ? { cursor: options.cursor } : {}),
      ...(options.includeTaskVersion ? { include_task_version: true } : {}),
    });
    return this.post<HarnessStateEnvelope>("/v1/runtime/state", body);
  }

  /** Prepare a new intent and retain the returned proof for all retries. */
  async prepareOperation(command: RuntimeCommand | WritebackDecisionRequest): Promise<OperationOrigin> {
    return this.post<OperationOrigin>("/v1/operations/prepare", JSON.stringify(command));
  }

  async readConsolidation(request: ConsolidationReadRequest): Promise<ConsolidationReadPage> {
    return this.post<ConsolidationReadPage>("/v1/consolidation/read", JSON.stringify(request));
  }

  async decideWriteback(
    request: WritebackDecisionRequest, operationOrigin: OperationOrigin,
  ): Promise<WritebackDecisionReceipt> {
    return this.post("/v1/consolidation/decision", JSON.stringify(request), this.originHeader(operationOrigin));
  }

  /** Submit an immutable prepared intent to managed intake. */
  async submitOperation(
    command: RuntimeCommand,
    operationOrigin: OperationOrigin,
    options: { transportMessageId?: string } = {},
  ): Promise<SpoolRecord> {
    return this.submitEvent(command, options, this.originHeader(operationOrigin));
  }

  private originHeader(operationOrigin: OperationOrigin): string {
    return JSON.stringify(operationOrigin).replace(
      /[\u007f-\uffff]/g,
      (character) => "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0"),
    );
  }

  /** Legacy intake carrier for hosts not yet composed with managed grants. */
  async submitEvent(
    command: RuntimeCommand,
    options: { transportMessageId?: string } = {},
    originHeader?: string,
  ): Promise<SpoolRecord> {
    const body = JSON.stringify({
      protocol_version: 1,
      command,
      ...(options.transportMessageId !== undefined
        ? { transport_message_id: options.transportMessageId }
        : {}),
    });
    return this.post<SpoolRecord>("/v1/runtime/intake", body, originHeader);
  }

  private async post<T>(route: string, body: string, originHeader?: string): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response: Response;
    try {
      response = await fetch(this.baseUrl + route, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${this.credential}`,
          ...(originHeader === undefined ? {} : { "Memorii-Operation-Origin": originHeader }),
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
    return (await response.json()) as T;
  }

}
