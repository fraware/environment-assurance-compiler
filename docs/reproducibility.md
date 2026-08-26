# Reproducibility

EnvAssure maintains two distinct reproducibility surfaces:

1. the published reproducibility bundle, whose recorded member digests can be
   verified without trusting an editable checkout; and
2. a cross-Python build study that independently builds the same canonical
   `.eap` on Python 3.11 and 3.12 and compares byte and semantic evidence.

Neither surface is evidence of production behavioral parity or EAC-R15
hidden-reference qualification.

## Reproducible `.eap` builds

`save_pack` follows the standard `SOURCE_DATE_EPOCH` convention. When the
variable is unset, ordinary packs retain their real UTC `created_at` timestamp
and the existing compressed ZIP representation. When it is set to a valid
non-negative Unix epoch:

- `manifest.json.created_at` is derived from that epoch in UTC;
- ZIP member order is deterministic;
- ZIP member timestamps are normalized to `1980-01-01T00:00:00` (the portable
  lower bound of the ZIP timestamp representation);
- member permissions and ZIP metadata are normalized; and
- members use `ZIP_STORED` rather than DEFLATE so linked-zlib differences cannot
  change archive bytes.

The build fails closed if `SOURCE_DATE_EPOCH` is malformed, negative, or outside
the supported Python datetime range.

For the same EnvAssure source, IR, pack inputs, runtime/policy versions,
metadata, and `SOURCE_DATE_EPOCH`, the release gate requires the Python 3.11 and
3.12 `.eap` archives to have the same SHA-256. This is an evidence-backed gate
for those two supported CI interpreters; it is not a claim about arbitrary
Python implementations, operating systems, filesystems, or future versions.

## Cross-Python evidence gate

`.github/workflows/cross-python-reproducibility.yml` independently builds the
canonical counter pack on Python 3.11 and 3.12, verifies each pack, and compares:

- full archive SHA-256;
- manifest and pack `content_digest`;
- every manifest member digest and size;
- embedded provenance and its canonical digest;
- verifier diagnostics; and
- a seeded deterministic runtime trace, including events, transaction receipts,
  observations, final state digest, and audit head.

The comparator is fail-closed. The only intentionally allowed difference is the
recorded `observed_platform.python_version`. Python implementation, operating
system, and machine architecture are recorded and must match within this CI
study; none of those platform observations are embedded into the canonical
pack.

Run the same study locally with two clean environments by setting the same
`SOURCE_DATE_EPOCH` and invoking:

```bash
python scripts/cross_python_reproducibility.py build --output-dir evidence
```

Then compare the two generated `evidence.json` files:

```bash
python scripts/cross_python_reproducibility.py compare \
  py311/evidence.json py312/evidence.json
```

## Published reproducibility bundle

The repository also ships `reproducibility/` with `MANIFEST.json`, expected
digests, environment/lock inputs, platform records, `reproduce.sh`, and
`verify.sh`.

From a full clone:

```bash
bash reproducibility/reproduce.sh
```

After extracting a published reproducibility bundle, `bash verify.sh` checks
recorded member digests without requiring the EnvAssure source checkout.

## Claim boundary

Digest verification proves artifact integrity relative to the recorded
commitments. Cross-Python equality demonstrates the declared canonical build
and seeded runtime evidence are reproducible under the tested 3.11/3.12 CI
environments. Neither establishes independent oracle concealment, scientific
qualification, deployment validity, or production parity.

## Related

- [Benchmarks](research/benchmarks.md)
- [Benchmark packs](packs/benchmark-packs.md)
- [Package and publish](guides/package-and-publish.md)
- [Release process](contributing/release-process.md)
