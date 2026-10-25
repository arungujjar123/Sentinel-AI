// Hex values for places CSS custom properties can't reach (Recharts SVG
// props). Keep in sync with the matching tokens in app/globals.css.
//
// Series pairs were checked with the dataviz palette validator against the
// card surface (#12151a, dark mode): both pairs pass lightness band, chroma
// floor, CVD separation (worst ΔE 26.8 / 17.3) and 3:1 contrast.
export const T = {
  surface: '#12151a',
  grid:    '#232830',
  axis:    '#343a43',
  ink:     '#eef0f3',
  ink2:    '#b4bac4',
  ink3:    '#8a919c',

  // Identity — one entity, one hue, everywhere it appears.
  groq:    '#3987e5',
  gemini:  '#d95926',
  hit:     '#199e70',
  miss:    '#9085e9',

  // Status — reserved for meaning, always paired with an icon + label.
  good:     '#0ca30c',
  warning:  '#fab219',
  serious:  '#ec835a',
  critical: '#d03b3b',
} as const

export function providerColor(name: string): string {
  if (name === 'groq') return T.groq
  if (name === 'gemini') return T.gemini
  return T.ink3
}
