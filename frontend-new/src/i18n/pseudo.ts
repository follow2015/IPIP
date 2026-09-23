const PSEUDO_MAP: Record<string, string> = {
  a: 'à', b: 'β', c: 'ç', d: 'δ', e: 'é', f: 'ƒ', g: 'ĝ', h: 'ĥ',
  i: 'í', j: 'ĵ', k: 'ķ', l: 'ł', m: 'ɱ', n: 'ñ', o: 'ó', p: 'þ',
  q: 'q', r: 'ŕ', s: 'š', t: 'ţ', u: 'ú', v: 'ṽ', w: 'ŵ', x: 'ẋ',
  y: 'ý', z: 'ž'
};

export function pseudoLocalize(value: string): string {
  return value.replace(/[a-zA-Z]/g, (ch) => {
    const mapped = PSEUDO_MAP[ch.toLowerCase()];
    if (!mapped) return ch;
    return ch === ch.toUpperCase() ? mapped.toUpperCase() : mapped;
  });
}
