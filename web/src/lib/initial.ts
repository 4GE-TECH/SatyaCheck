/** Preserve combining marks and emoji sequences in the visible avatar. */
export function initial(name: string): string {
  const value = name.trim();
  if (!value) return '?';
  const first = typeof Intl.Segmenter === 'function'
    ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(value)[Symbol.iterator]().next().value?.segment
    : Array.from(value)[0];
  return (first || '?').toLocaleUpperCase();
}
