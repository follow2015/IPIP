import dayjs from 'dayjs';

const MAX_NAME_LENGTH = 128;

export type DefaultNameDevice = {
  device_name?: string | null;
  device_type?: string | null;
};

function normalizeSegment(value: unknown): string {
  return String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function buildDefaultCredentialName(
  protocol: string,
  devices: readonly DefaultNameDevice[],
  now: Date = new Date()
): string {
  const prefix = normalizeSegment(protocol).toUpperCase();
  const suffix = dayjs(now).format('MMDD');

  const first = devices[0];
  const deviceSegment =
    normalizeSegment(first?.device_name) || normalizeSegment(first?.device_type);

  if (!deviceSegment) {
    return `${prefix}-${suffix}`;
  }

  const budget = MAX_NAME_LENGTH - prefix.length - suffix.length - 2;
  const segment = budget > 0 ? deviceSegment.slice(0, budget) : '';
  return segment ? `${prefix}-${segment}-${suffix}` : `${prefix}-${suffix}`;
}
