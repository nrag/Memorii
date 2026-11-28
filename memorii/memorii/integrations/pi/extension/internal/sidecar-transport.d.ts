export type SidecarRequest = (
  route: string,
  body: Record<string, unknown>,
  origin?: string,
) => Promise<unknown>;

export function createSidecarTransport(
  url: string,
  credentialPath: string,
): <T>(callback: (request: SidecarRequest, binding: string) => Promise<T>) => Promise<T>;

export function resumeTask(
  request: SidecarRequest,
  binding: string,
  scope: { kind: "pi" | "openclaw"; taskId: string; sessionId: string },
): Promise<void>;

export function capturedObservation(receipt: unknown, taskId: string): boolean;
export function recalledUserData(envelope: unknown): string | undefined;
