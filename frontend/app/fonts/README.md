# Bundled brand fonts

These unmodified font files come from the official
[Google Fonts repository](https://github.com/google/fonts/tree/7085eb89a950e85db5b166b7a58d414544b4140c),
pinned to commit `7085eb89a950e85db5b166b7a58d414544b4140c`.

| Local file                | Upstream file                             | Weights |
| ------------------------- | ----------------------------------------- | ------- |
| `Sora-Variable.ttf`       | `ofl/sora/Sora[wght].ttf`                 | 100–800 |
| `IBMPlexMono-Regular.ttf` | `ofl/ibmplexmono/IBMPlexMono-Regular.ttf` | 400     |
| `IBMPlexMono-Medium.ttf`  | `ofl/ibmplexmono/IBMPlexMono-Medium.ttf`  | 500     |

`Sora-OFL.txt` and `IBMPlexMono-OFL.txt` preserve the corresponding upstream
copyright notices and SIL Open Font License 1.1. Keep them with the font files.

The root layout uses `next/font/local` to emit and preload these assets. This
removes Google Fonts requests from development and production builds, preventing
transient upstream responses from breaking CI. CSS variables and `display: swap`
remain the same. Update fonts intentionally from a pinned upstream commit, and
verify a production build before committing replacements.
