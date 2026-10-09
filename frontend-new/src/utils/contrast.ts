
export function lum(v: string): number {
  const s = v.trim();
  let hex = '';
  if (/^#[0-9a-fA-F]{6}$/.test(s)) hex = s.toLowerCase();
  else if (/^#[0-9a-fA-F]{3}$/.test(s))
    hex =
      '#' +
      s
        .slice(1)
        .split('')
        .map((c) => c + c)
        .join('')
        .toLowerCase();
  else {
    const m = s.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/);
    if (!m) throw new Error(`Unparsable color value: ${v}`);
    const a = m[4] === undefined ? 1 : Number(m[4]);
    const over = a < 1 ? [0x18, 0x1b, 0x1f] : [255, 255, 255];
    hex =
      '#' +
      [Number(m[1]), Number(m[2]), Number(m[3])]
        .map((c, i) =>
          Math.round(c * a + over[i] * (1 - a))
            .toString(16)
            .padStart(2, '0')
        )
        .join('');
  }
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const la = lum(a);
  const lb = lum(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}
