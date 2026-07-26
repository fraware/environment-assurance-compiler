# Limitations

- This scaffold records pack manifests and local platform metadata. Full
  release-manifest coordinates (wheel/sdist/OCI digests, Cosign attestations)
  are attached by the signed-tag release pipeline when Milestone A lands.
- Hidden oracle episodes for benchmark packs remain digest-pinned and are not
  shipped as answer keys inside this bundle.
- `verify.sh` proves digest integrity of the bundle members. It does not claim
  production behavioral parity of any environment.
- Hardware/platform fields reflect the machine that last refreshed the bundle;
  CI refresh overwrites them on each reproduce job.
