import type { AxiosError } from 'axios';

interface BackendErrorBody {
  error_code?: string;
  message?: string;
}

function shapeOf(err: unknown): { status?: number; body?: BackendErrorBody } {
  if (!err || typeof err !== 'object') return {};
  const e = err as AxiosError<BackendErrorBody>;
  return { status: e.response?.status, body: e.response?.data };
}

export function getApiErrorCode(err: unknown): string | null {
  const { body } = shapeOf(err);
  return typeof body?.error_code === 'string' ? body.error_code : null;
}

export function getApiErrorMessage(err: unknown): string | null {
  if (err instanceof Error && err.message) return err.message;
  const { body } = shapeOf(err);
  return typeof body?.message === 'string' ? body.message : null;
}

export function isHttpStatus(err: unknown, status: number): boolean {
  return shapeOf(err).status === status;
}
