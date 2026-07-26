# Transactional Refund Benchmark Pack

Concealed multi-step refund / ledger workflow with idempotency and retry conflict probes. Maps to concealed suite transactional_enterprise.

- Pack ID: `envassure-transactional-refund`
- Workflow: `transactional_enterprise`
- Hidden oracle digest: `de35098a6adb1c28860e9b56ff040a3f8b49fd240ae4a46365094e42d8bef8e8`

## Commands

```bash
eac pack lint packs/envassure-transactional-refund
eac pack verify packs/envassure-transactional-refund
eac pack inspect packs/envassure-transactional-refund --json
eac pack reproduce packs/envassure-transactional-refund -o /tmp/repro
eac benchmark benchmarks/fixtures/transactional_enterprise.json --json
```
