# Release Wheel and Docker Image

Release `v0.1.0` is available with a Linux amd64 image. The multi-architecture
workflow described here applies to subsequent releases after its dry run and
review. It does **not** modify the existing `v0.1.0` tag, digest or release assets.
Each new release must be explicitly published by a maintainer. This prototype
is not a production security certification.

## Deliverables

For a new stable tag, the workflow produces these artifacts (substitute the
actual release version for `<version>`):

| Location | Artifact |
| --- | --- |
| GitHub Release | `agent_native_graph-<version>-py3-none-any.whl` |
| GitHub Release | `agent_native_graph-<version>.tar.gz` (source distribution) |
| GitHub Release | `SHA256SUMS` (the wheel and source hashes) |
| GitHub Release | `image-digest.txt` (the published multi-architecture index digest) |
| GHCR | `ghcr.io/paoloalbano/agent-native-graph:<version>` (amd64 + arm64 index) |
| GHCR | `ghcr.io/paoloalbano/agent-native-graph:<version>-amd64` |
| GHCR | `ghcr.io/paoloalbano/agent-native-graph:<version>-arm64` |

There is no automatic PyPI upload, `latest` tag or moving minor-version alias.
Only stable `vX.Y.Z` releases are supported in this first workflow. Prerelease
events cannot publish. The Python wheel is pure Python for Python 3.11+.
The updated workflow targets **Linux amd64 and arm64**, including Apple Silicon
without amd64 emulation. Docker selects the matching platform from the shared
version tag; architecture-specific tags are available for explicit selection.
The already-published `0.1.0` image remains amd64-only.

## Native Build and Test Gates

1. The `build` job checks the code, builds one wheel/source pair and uploads
   `python-distributions` with checksums. The image jobs do not rebuild the wheel.
2. The `images` matrix runs `linux/amd64` on `ubuntu-24.04` and `linux/arm64`
   on `ubuntu-24.04-arm`. Each verifies the same downloaded checksums, builds
   its native image, checks its OS/architecture and runs all five distribution
   tests on an isolated native Neo4j. No QEMU or model inference is needed.
3. Each successful branch saves its tested image as `tested-image-amd64` or
   `tested-image-arm64`. If either branch fails, `publish` cannot run.
4. On a release event only, `publish` downloads both images, verifies their
   platforms and pushes them without rebuilding. It creates the shared index
   from their registry digests, verifies that it contains exactly the two
   expected platforms, and records the index digest in `image-digest.txt`.

Docker/Buildx may also preserve attestation manifests marked `unknown/unknown`.
These metadata entries are retained but excluded from the runnable-platform
check; the executable images must still be exactly Linux amd64 and arm64.

Manual workflow runs execute steps 1-3 without pushing either image or the
index. Native runner coverage is confirmed by the remote dry run, not merely
by an emulated local build.

## Maintainer Procedure

1. Update `project.version` in `pyproject.toml` for a new release and run
   `uv lock` to update the local package version in `uv.lock`. Keep both files
   in the PR. Do not reuse `v0.1.0`: it is already published.
2. Run the local checks below, then choose **Actions > Release artifacts > Run
   workflow** on your feature branch, with a tag matching its package version.
   This input validates the checked-out branch; it does not fetch or create a
   tag. A manual run **never publishes**, even on `main`.
3. Review the workflow, its checks and downloadable `python-distributions`
   artifact. Merge the reviewed code into `main` only after checks pass.
4. In GitHub Releases, create a release using a new `vX.Y.Z` tag on the reviewed
   `main` commit. Publish it explicitly. That `release: published` event runs
   the build/tests again on the tagged code and then publishes the tested
   artifacts. This upload-based workflow cannot handle already-immutable
   releases and rejects them before building or publishing any artifacts:
   assets are attached after the published event. If your repository requires
   immutable releases, stop here and implement draft promotion first; do not
   weaken repository rules to run this workflow. See GitHub's
   [immutable release procedure](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
5. Confirm the release workflow succeeds, the four release assets exist, and
   the GHCR package can be pulled anonymously. Check its visibility in GitHub
   Packages settings and make it public if necessary. Repository visibility
   alone is not a substitute for verifying package access.

Publishing the release starts the workflow; the release page can therefore
exist temporarily without its assets. If a gate fails, nothing is published by
the publish job. Publishing to GHCR and attaching GitHub assets are separate
operations, not an atomic transaction: if upload fails after the image push,
inspect the partial state before retrying. Architecture-specific tags may
exist if publication fails before the shared index is created. Do not move a released tag or reuse
a version for different code. Asset uploads deliberately omit `--clobber`.
If repository rules enforce immutable releases, use a future draft-release
promotion workflow instead of bypassing those rules.

Authentication uses the workflow's `GITHUB_TOKEN`: `contents: write` to attach
release assets and `packages: write` for GHCR. The build and matrix jobs have only
`contents: read`. No Docker Hub password, model key or external graph credentials
are needed. Restrict who can create repository releases. GitHub environments
and additional approval gates can be added later if needed.

## Local Checks (No Publication)

```bash
make sync
make lint
make test
make build
make check-release RELEASE_TAG=v0.1.0
make test-distribution
```

Use a clean `dist/`: the audit rejects old or unrelated artifacts. It checks
tag/project/lock agreement, wheel metadata, package/profile inclusion and
distribution allowlists before writing `SHA256SUMS`. Source archives exclude
results, datasets, documentation builds, tests and local investigation folders.
This inventory check is not a general secret scanner; review package source
before releasing it.

`make test-distribution` uses its own disposable synthetic Neo4j. It does not
connect to Company, call an LLM or require benchmark files. See the
[distribution test coverage](library-and-server.md#reproducible-distribution-smoke).

The release jobs install the source distribution in a fresh environment,
install the wheel outside the checkout and test both actual HTTP images.
For a local check, select the native architecture of your Docker host (`arm64`
on Apple Silicon, `amd64` on Intel/AMD Linux). Docker's named context selects
the already-built wheel:

```bash
ARCH=arm64
docker buildx build --load --platform "linux/$ARCH" \
  --build-context wheels=./dist --tag ana-release:test .
ANA_TEST_DIST_DIR="$PWD/dist" ANA_TEST_SERVICE_IMAGE=ana-release:test \
  make test-distribution
```

These overrides are for local/CI artifact verification. The fixture leaves an
externally supplied image in place; it still removes only the containers and
network it creates. Remove `ana-release:test` yourself when finished.
Ordinary `make docker-build` needs no `dist/`: the Dockerfile builds a wheel
internally and installs it into the runtime. Neither path runs editable source.
Service dependencies come from `uv.lock`; the runtime does not contain the
checkout, datasets, results or credentials.

The workflow saves both tested images and passes them to the separate publish job.
That job loads and pushes them without rebuilding. The same wheel bytes are
uploaded as a release asset. Dry-run workflow artifacts expire according to
GitHub retention settings (both large image artifacts are retained for three days).

## Install a Published Release

These commands work **only after the corresponding release has completed**.
For the library, download the wheel and `SHA256SUMS` from the GitHub Release
(download the source archive too if checking the full checksum file):

```bash
sha256sum --check SHA256SUMS
uv venv
uv pip install ./agent_native_graph-0.1.0-py3-none-any.whl
```

On macOS use `shasum -a 256 -c SHA256SUMS`. For the HTTP extra, install
`'./agent_native_graph-0.1.0-py3-none-any.whl[service]'` instead. PyPI name-based
installation is not promised by this workflow.

To use the prebuilt container, replace the source-built image in the
[server instructions](library-and-server.md#http-server) with:

```bash
docker pull ghcr.io/paoloalbano/agent-native-graph:0.1.0
```

That first release is amd64-only. After a new multi-architecture release is
published, replace `0.1.0` with its version and Docker will choose amd64 or arm64
automatically. No existing published version is silently upgraded by this change.

Keep the same authentication file mount, Neo4j environment variables and
loopback port mapping; the image bundles neither Neo4j nor graph data. For
reproducible deployments use `ghcr.io/paoloalbano/agent-native-graph@sha256:...`
from `image-digest.txt`, rather than relying on a tag alone. An existing Neo4j
instance is still required. The current one-worker/session-local limitations
remain unchanged.
