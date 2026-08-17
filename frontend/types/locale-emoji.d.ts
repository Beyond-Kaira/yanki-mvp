// locale-emoji ships no types of its own, and there is no @types package.
declare module 'locale-emoji' {
  /** Flag for a locale id, or an empty string for a language with no region
   * (Esperanto, Volapük and the other constructed ones). */
  export default function localeEmoji(locale: string): string
}
