# Yanki — auto-deploy on merge to `main`

> **Status: LIVE (2026-07-28).** Merging a pull request into `main` ships it to
> <https://yanki.beyondkaira.com> with no human step, provided CI is green.
> Before this, deployment was entirely manual: someone SSHed in and ran
> `deploy/deployment.sh`. The symptom was drift — on the day this was built the
> live containers were running `d6514ee` while `main` was six commits ahead.

## The chain

```
PR merged
  └─ ci.yml            (push:main)  backend · frontend · contract · gitleaks · e2e
       └─ deploy.yml   (workflow_run: CI completed && conclusion == success)
            └─ ssh aytek@161.97.172.146  "deploy <40-hex-sha>"
                 └─ ~/.local/bin/yanki-ci-deploy      ← forced command, not a shell
                      └─ ~/deploy/yanki-mvp           ← dedicated prod checkout
                           └─ deploy/deployment.sh    ← build · up · health · record
```

Roughly CI time + build time from merge to live. **Deploy waits for CI on
purpose.** The api container runs `alembic upgrade head` on boot, so a broken
migration reaching production is not something the health-gate rollback can
undo — the cheap insurance is to never ship a red commit.

## Why the runner cannot do anything else to the host

`DEPLOY_SSH_KEY` is not a login. Its public half is pinned in
`~/.ssh/authorized_keys` as:

```
command="/home/aytek/.local/bin/yanki-ci-deploy",restrict ssh-ed25519 AAAA… yanki-ci-deploy
```

- `command=` — sshd runs **that wrapper and nothing else**, whatever the client
  asks for. The client's string arrives only as `$SSH_ORIGINAL_COMMAND`, as data.
- `restrict` — no pty, no agent/port/X11 forwarding, no `~/.ssh/rc`.
- The wrapper accepts exactly two requests, `ping` and `deploy <40-hex-sha>`,
  and **refuses any sha that is not already an ancestor of `origin/main`**.

So the blast radius of a leaked secret is "redeploy a commit that is already on
main" — not shell on a box that also hosts pulse-prod, brier, antmedia and
evrak-app. Verified by construction at install time: arbitrary commands, a bare
connection, malformed shas, off-main shas and `deploy <sha>; rm -rf …` all exit
2 without running anything.

The wrapper *runs* from **outside the repo** deliberately. The deploy checks out
`main`, so anything executed from in-tree is content the wrapper is supposed to
be guarding; a wrapper run out of `deploy/` could be rewritten by the very commit
it is meant to validate.

[`deploy/host/yanki-ci-deploy`](host/yanki-ci-deploy) is therefore a **tracked
reference copy, not the live one** — the same arrangement as the nginx vhost.
Editing it changes nothing until a human installs it, which is the point:

```bash
# Install / update the live copy after changing the tracked one
install -m 700 deploy/host/yanki-ci-deploy ~/.local/bin/yanki-ci-deploy

# Drift check — tracked vs. what actually runs
diff ~/.local/bin/yanki-ci-deploy deploy/host/yanki-ci-deploy && echo in-sync
```

## Server-side layout

| Path | What it is |
|---|---|
| `~/deploy/yanki-mvp` | the prod checkout CI drives (detached HEAD, always a sha on main) |
| `~/repo/yanki-mvp` | the human working tree — **auto-deploy never touches it** |
| `~/deploy/yanki-mvp/deploy/.env` | symlink → `~/repo/yanki-mvp/deploy/.env` (one canonical secrets file, no drift) |
| `~/deploy/yanki-mvp/deploy/.last-good` | rollback target, seeded from the manual era at `d6514ee` |
| `~/.local/bin/yanki-ci-deploy` | the forced command |
| `~/.local/state/yanki-ci-deploy.log` | append-only deploy log, timestamped UTC |
| `~/.local/state/yanki-prod-deploy.lock` | the one deploy lock — see below |

The compose project name is fixed (`-p yanki-prod`), so driving the stack from
the new checkout manages the *same* containers the manual deploys did.

## Image pruning — why it is part of the deploy

Every deploy builds `yanki-api:<sha>` (~550MB) and `yanki-web:<sha>` (~1.6GB).
A single day of manual deploys had already left 28 stale images on a disk with
28GB free; at one build per merge that fills up and takes the co-tenant services
down with it. The wrapper therefore prunes after each successful deploy, keeping
the newest three tags per repository **plus** the sha just deployed, the
`.last-good` sha and `latest`. It only ever considers `yanki-api` / `yanki-web`,
and ignores `docker rmi` failures — an image still referenced by a running
container refuses to delete, which is the last safety net.

**Not pruned: the buildx cache**, and it is the real disk risk — it was already
37GB when this was built. The wrapper does not touch it, because that cache is
shared with every other build on the box and silently reclaiming it is not
auto-deploy's call. Instead the wrapper **refuses to start a build with less
than 10GB free** and tells you what to do:

```bash
docker system df                              # where the space actually went
docker buildx prune --filter until=168h       # the usual reclaim
```

A refusal fails the `Deploy` run and pages Slack — which is the point. Filling
this disk does not just fail a deploy, it takes the co-tenants down.

## One lock, two drivers

Two things now drive the `yanki-prod` compose project: CI, and a human running
`make deploy`. Run at once they interleave two releases, and the surviving
containers and the recorded `.last-good` can end up describing different code.

Both therefore take the same `flock` on
`~/.local/state/yanki-prod-deploy.lock`, waiting up to 900s:

- the CI wrapper takes it **before** it checks out a sha, since the checkout has
  to be inside the lock too, and passes `YANKI_DEPLOY_LOCK_HELD=1` down so
  `deployment.sh` does not deadlock against it;
- a human's `deployment.sh` takes it itself, after `--check` (which is read-only
  and never blocks).

So a hand deploy started during a CI deploy waits its turn instead of racing it.
`rollback.sh` invoked directly is the one path outside this — it is the
emergency lever, and it is meant to work even when everything else is stuck.

## What is still manual

1. **Edge config.** `deploy/nginx/yanki.beyondkaira.com.conf` needs `sudo` to
   install and the deploy key deliberately has none. A change there is still
   `sudo cp` + `sudo nginx -t` + `sudo systemctl reload nginx` (never restart) —
   see item 7 of [`docs/tech-debt.md`](../docs/tech-debt.md).
2. **Secrets.** `deploy/.env` is gitignored and lives only on the host.
   Adding a key is a manual edit; `scripts/check_env.py` gates the deploy on it.

## Operating it

```bash
# Redeploy without pushing a commit (Actions → Deploy → Run workflow),
# optionally pinning a sha; blank means the current tip of main.
gh workflow run Deploy --repo Beyond-Kaira/yanki-mvp

# Watch the server side
tail -f ~/.local/state/yanki-ci-deploy.log

# Roll back by hand (the deploy already self-rolls-back on failure)
~/deploy/yanki-mvp/deploy/rollback.sh
```

A failed `Deploy` run pages Slack through `notify.yml` (its `workflows:` list
includes `Deploy` for exactly this reason).

## Rotating or revoking the key

```bash
# Revoke: drop the forced-command line from authorized_keys. Takes effect on the
# next connection — no sshd reload needed.
sed -i '/yanki-ci-deploy$/d' ~/.ssh/authorized_keys

# Rotate: regenerate, re-pin the forced command, re-upload the private half.
ssh-keygen -t ed25519 -N '' -C yanki-ci-deploy -f ~/.ssh/yanki-ci-deploy
printf 'command="/home/aytek/.local/bin/yanki-ci-deploy",restrict %s\n' \
  "$(cat ~/.ssh/yanki-ci-deploy.pub)" >> ~/.ssh/authorized_keys
gh secret set DEPLOY_SSH_KEY --repo Beyond-Kaira/yanki-mvp < ~/.ssh/yanki-ci-deploy
```

Never paste the private key into a file in this repo: it is public, and CI runs
gitleaks over the **full history** with `--exit-code 1`.

## When a deploy fails

`deployment.sh` rolls back to `.last-good` on every failure path, then re-probes
the public health url so a rollback that did not actually restore service still
exits non-zero. Read, in order:

1. The `Deploy` run in the Actions tab — distinguishes "could not reach the
   host" (the `Reach the host` step) from "the deploy itself failed".
2. `~/.local/state/yanki-ci-deploy.log` on the VPS.
3. `deploy/deploy-logs.sh` for container logs.

If the rollback itself failed, the log says so explicitly and the stack needs
hands-on recovery — that is the one case nothing here can automate.
