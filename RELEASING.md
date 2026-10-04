# Releasing alogs-cli

Releases are built and published by GitHub Actions
([`.github/workflows/release.yml`](.github/workflows/release.yml)) when a tag `v<version>` is
pushed. Nothing is published by ordinary pushes; [`ci.yml`](.github/workflows/ci.yml) only runs
the tests (Windows / macOS / Linux × Python 3.10–3.13).

No PyPI token is stored anywhere: the upload uses PyPI **trusted publishing** — GitHub hands the
workflow a short-lived signed identity, PyPI checks it is this repository + `release.yml` +
environment `pypi`, and accepts the upload.

## One-time setup

1. **GitHub URLs** in `pyproject.toml` point to `https://github.com/hodinv/alogs-cli` (done). If
   the repository ever moves, change them there — the release check fails if a placeholder
   `OWNER/` reappears.
2. **GitHub repository** `hodinv/alogs-cli` (public, so Actions minutes are free); push the code.
   Check the *Actions* tab: the CI workflow should go green on all 12 jobs.
3. **GitHub environment** (*Settings → Environments → New environment*): name it `pypi`.
   Recommended: tick *Required reviewers* and add yourself — every PyPI upload then waits for
   your click. Optionally restrict *Deployment branches and tags* to tags `v*`.
4. **PyPI account** at <https://pypi.org/account/register/>: verify the e-mail and enable
   two-factor authentication (mandatory for uploading).
5. **Pending trusted publisher** on PyPI (*Your account → Publishing → Add a new pending
   publisher → GitHub*):

   | Field | Value |
   |---|---|
   | PyPI Project Name | `alogs-cli` |
   | Owner | `hodinv` |
   | Repository name | `alogs-cli` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   "Pending" means the project does not exist yet; the first successful upload creates it and
   reserves the name for you.

Optional dry run: create a TestPyPI account (<https://test.pypi.org>, separate from PyPI), add the
same pending publisher there, and temporarily add `with: repository-url:
https://test.pypi.org/legacy/` to the `pypa/gh-action-pypi-publish` step.

## Each release

```sh
# 1. bump the version — the only place it lives
#    alogs/__init__.py:  __version__ = "0.2.0"
uv lock                               # refresh uv.lock (it records the project version)
uv run pytest                         # optional local check
git commit -am "Release 0.2.0"
git push

# 2. tag and push the tag — this starts the release workflow
git tag v0.2.0
git push origin v0.2.0
```

Then on GitHub → *Actions → Release*:

1. `check` — fails if the tag is not `v` + `__version__` (or a placeholder `OWNER/` is back in `pyproject.toml`).
2. `test` on Windows, macOS, Linux.
3. `dist` builds wheel + sdist and smoke-tests the wheel; `binaries` builds and self-tests the
   single-file executables on the three OSes.
4. `publish-pypi` waits for your approval (if you set required reviewers) → *Review deployments
   → Approve*. A minute later `uv tool install alogs-cli` installs the new version.
5. `github-release` creates the GitHub release `v0.2.0` with the three binaries, the wheel and
   the sdist, and notes generated from the commits.

Versions look like `0.2.0`, `1.0.0`, or pre-releases `1.0.0rc1` (tag `v1.0.0rc1`; marked as a
pre-release on GitHub, and `uv tool install` skips it unless asked for explicitly).

## If something goes wrong

- **A job failed before `publish-pypi`:** nothing was published. Fix, delete the tag
  (`git tag -d v0.2.0 && git push origin :refs/tags/v0.2.0`), commit, tag again.
- **PyPI already has the version:** PyPI never accepts the same version twice, even after you
  delete it there. Bump to `0.2.1` and release again.
- **`publish-pypi` fails with an "invalid publisher" error:** the five trusted-publisher values
  on PyPI must match exactly (owner, repository, `release.yml`, `pypi`).
- **Binaries:** macOS binaries are built on Apple-silicon runners (`arm64`); Intel Macs use
  `uv tool install alogs-cli`. Binaries are not code-signed, so macOS Gatekeeper and Windows
  SmartScreen warn once (signing needs an Apple Developer account / a code-signing certificate).
