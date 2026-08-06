// Leaving the app entirely — the one navigation Next's router cannot do.
//
// `router.push` moves within this application. Sending the browser to
// accounts.google.com is a full-page departure, so it has to go through
// `window.location`. That is a single line, and it lives here rather than
// inline for one reason: jsdom does not implement navigation, and
// `window.location` is not reliably patchable in it, so a component calling it
// directly cannot be tested at all without weakening the component.
//
// This indirection changes nothing at runtime. It gives the test a seam
// (`vi.mock('@/lib/navigation')`) instead of asking production code to accept
// an injectable navigator it would never be given in production.

export function redirectToExternal(url: string): void {
  window.location.assign(url)
}
