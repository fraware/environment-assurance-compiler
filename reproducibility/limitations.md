# Limitations

- The cross-Python reproducibility gate currently establishes its strongest
  claim only for the repository's Ubuntu CI environments on CPython 3.11 and
  3.12. It is not evidence of universal byte identity across operating systems,
  Python implementations, future interpreter versions, or arbitrary filesystems.
- Reproducible `.eap` mode is opt-in through a fixed `SOURCE_DATE_EPOCH`.
  Ordinary builds intentionally preserve a real UTC `created_at` timestamp and
  therefore are not expected to be byte-identical across invocations.
- Reproducible mode uses `ZIP_STORED` and normalized ZIP metadata to remove
  compressor and wall-clock variability. The manifest still records the
  requested source epoch; the ZIP member timestamp is fixed to 1980-01-01 for
  portable deterministic encoding.
- In cross-Python evidence, `observed_platform.python_version` is the only
  intentionally permitted difference. Python implementation, OS, and machine
  architecture are recorded and required to match within the CI comparison.
- `verify.sh` proves digest integrity of the published reproducibility-bundle
  members relative to their recorded commitments. It does not establish
  production behavioral parity, independent hidden-reference concealment, or
  EAC-R15 scientific qualification.
- Hidden oracle episodes for benchmark packs remain digest-pinned and are not
  shipped as answer keys inside this bundle.
- Full release-manifest coordinates and external supply-chain attestations are
  governed by the signed-tag release pipeline; their existence must not be
  inferred from this reproducibility study alone.
