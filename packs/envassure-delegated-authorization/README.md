# Delegated Authorization Benchmark Pack

Concealed multi-tenant approval workflow emphasizing deny-path preservation and observation separation. Maps to authorization_heavy.

- Pack ID: `envassure-delegated-authorization`
- Workflow: `authorization_heavy`
- Hidden oracle digest: `f8f4cca23463774f8cf41b292c916e4d2c9696abbf328aec09fdf163b3b1b455`

## Commands

```bash
eac pack lint packs/envassure-delegated-authorization
eac pack verify packs/envassure-delegated-authorization
eac pack inspect packs/envassure-delegated-authorization --json
eac pack reproduce packs/envassure-delegated-authorization -o /tmp/repro
eac benchmark benchmarks/fixtures/authorization_heavy.json --json
```
