/** What a customer sees when the module is switched off.
 *
 * This is the common case in production today, not an edge case, so it is a
 * first-class state rather than an error card: `BACKLINKS_ENABLED` is off until
 * a licensed index is contracted, and a page that renders "something went
 * wrong" for a deliberate configuration would generate support tickets about a
 * system that is working exactly as intended.
 *
 * It also does not promise a date. The nav's own rule is that we may not
 * advertise something that does not exist, and "coming soon" with a timeline
 * nobody has committed to is the same mistake one level down.
 */
export default function BacklinksDisabledNotice({ domain }: { domain?: string }) {
  return (
    <section className="rounded-xl border border-surface-border bg-surface p-8 shadow-sm">
      <h2 className="text-xl font-semibold text-surface-foreground">
        Backlinks are not switched on yet
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-surface-subtle">
        Backlink data comes from a licensed index, and this workspace is not
        connected to one yet
        {domain ? <> for <span className="font-medium">{domain}</span></> : null}. The
        analysis itself is built and tested — discovery, new and lost links,
        referring domains, anchors, authority and toxicity — and switches on for
        every project at once when an index is connected.
      </p>
      <p className="mt-4 max-w-2xl text-sm text-surface-subtle">
        Nothing is being collected or charged in the meantime.
      </p>
    </section>
  )
}
