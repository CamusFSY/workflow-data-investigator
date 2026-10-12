# GitHub Pages publication proposal

**Review candidate only. No public branch, PR, merge, settings change or deployment
has been made.** The only publication target is the public repository
`CamusFSY/workflow-data-investigator`.

Expected URL after an approved successful deployment:
`https://camusfsy.github.io/workflow-data-investigator/`.
This is a proposed URL, not a claim that a site is live.

## Exact denied read and present state

The normal shell tool ran:

```sh
gh api repos/CamusFSY/workflow-data-investigator/pages
```

Target: `GET https://api.github.com/repos/CamusFSY/workflow-data-investigator/pages`.
The complete returned error was:

```text
Get "https://api.github.com/repos/CamusFSY/workflow-data-investigator/pages": Forbidden
```

No automatic approval rejection appeared. The failure surfaced inside the CLI
request; no response status, body or request ID identified whether it came from
GitHub permissions or an intervening transport policy. Current Pages settings
are **unknown**, not asserted disabled. This read has not been retried. The
available GitHub connector has no Pages administration action. No alternate
credentials or access-policy bypass were attempted.

## Recommended minimal configuration, pending parent review

This site is a prebuilt static artifact; it needs no repository-authored deploy
workflow. After reviewing the integrated paper, source diff, video and artifact:

1. An authorized maintainer inspects the existing Pages settings and protection
   rules. Any conflict with an existing site, domain or environment restriction
   returns to review; no setting is silently weakened.
2. Publish the reviewed feature branch to this public repository and open a PR.
   Merge only after explicit approval and required checks.
3. Build the allowlisted artifact from the reviewed source commit with
   `python3 scripts/build_showcase.py --out dist/pages-release`, then run
   `python3 scripts/check_showcase.py dist/pages-release` and browser verification.
4. After separate publication approval, commit **only the generated artifact** to
   a dedicated `gh-pages` branch at its root, using the already authorized public
   repository. Include `.nojekyll`. Do not copy a checkout, private ancestry,
   experimental packets, raw live traces or credentials. Do not force-push over
   an existing branch; inspect and preserve any existing publication first.
5. In **Settings → Pages → Build and deployment**, choose **Source: Deploy from
   a branch**, **Branch: gh-pages**, **Folder: /(root)**, then save. The exact
   equivalent settings payload is:

   ```json
   {"build_type":"legacy","source":{"branch":"gh-pages","path":"/"}}
   ```

   `legacy` is GitHub's API name for branch publishing. It does not refer to the
   application's legacy finish mode. The branch must exist before selection.
6. Inspect GitHub's resulting managed Pages deployment and verify the actual
   site URL, links and playback. A successful local build is not deployment proof.

Branch publishing avoids adding custom-workflow `pages: write` and
`id-token: write` permissions. GitHub still uses its managed Actions deployment;
`.nojekyll` skips Jekyll processing. It does **not** eliminate the initial Pages
configuration permission requirement or circumvent the denied read. Future
pushes to the selected publishing branch can publish immediately and therefore
remain deliberate publication actions. Pushes made by a workflow's `GITHUB_TOKEN`
do not trigger this branch-based Pages build.

Preserve repository visibility, custom domains, branch/environment protections,
organization policy, default token permissions and all secrets. This proposal
requests no broader credential scopes. Use the authorized maintainer settings UI
for initial configuration; if it remains unavailable, publication stays blocked.
No separate Sites deployment and no application resubmission are proposed.

## Alternative considered

A manual `workflow_dispatch` Pages workflow would need `contents: read`, with
`pages: write` and `id-token: write` limited to its deployment job and a protected
`github-pages` environment. This adds permissions that this static site does not
need in a repository-authored workflow. The earlier draft workflow is omitted
from this candidate; adopting that alternative would require a separate review.

## Artifact and evidence boundary

The build copies an explicit file list, the current paper PDF with its figures
and notices, and a fresh replay-verified run over the original synthetic fixture.
The video retains its prominent **OFFLINE RECORDED RESPONSES** disclosure.
No application runtime behavior or historical evaluation denominator changes.
The public base is `fd6d35392969ff8f34d7c7de548fc943283e4f3b`, tree
`4fdec84e9e5bbc822a1b94771c7d276895f7e0ae`; the candidate has public ancestry only.

Sources: GitHub's [publishing-source guide](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
and [Pages REST API](https://docs.github.com/en/rest/pages/pages).
