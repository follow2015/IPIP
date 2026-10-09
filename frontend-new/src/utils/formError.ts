
interface ErrorField {
  errors?: string[];
  name?: (string | number)[];
}

interface ValidateErrorLike {
  errorFields?: ErrorField[];
}

function asValidateError(err: unknown): ValidateErrorLike | null {
  if (!err || typeof err !== 'object') return null;
  return 'errorFields' in err ? (err as ValidateErrorLike) : null;
}

export function isValidationError(err: unknown): boolean {
  return asValidateError(err) !== null;
}

export function firstFieldError(err: unknown): string | undefined {
  const e = asValidateError(err);
  const first = e?.errorFields?.[0];
  const msg = first?.errors?.[0];
  return typeof msg === 'string' && msg.length > 0 ? msg : undefined;
}
