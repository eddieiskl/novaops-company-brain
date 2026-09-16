# Lesson 14: vendor serving extension

HTTP `/v1/vendor/extract` and `novaops-vendor-worker` share `vendor.runtime.extract_request`. Existing deterministic fixtures still assert 0, 1 and 2 missing required CRM fields.

Direct Bedrock calls disable SDK retries and have 5-second connect / 30-second read timeouts. The extractor retries only named transient botocore ClientErrors, at most three attempts with bounded full jitter. Access-denied, validation and gateway HTTP errors are not retried here; gateway transport retry policy remains owned by LiteLLM. Exhaustion re-raises the original provider exception.

Model output is normalized and schema-validated locally. Invalid output gets exactly one additional repair request with the original source and validation feedback, then raises `VendorSchemaError`. Empty or malformed record objects cannot silently become an all-null CRM record. Each of the two possible model requests has its own maximum three-attempt direct-provider transport budget (six provider attempts maximum).

## Queue adapter

Set `NOVAOPS_MODEL_BACKEND=bedrock` (or deterministic for fixture tests), `VENDOR_INPUT_QUEUE_URL`, `VENDOR_RESULT_QUEUE_URL`, and `VENDOR_CACHE_PATH`, then run:

```sh
python -m vendor.worker
```

Use a standard result queue and configure input-queue redrive to a DLQ. One consumer handles one message at a time with a 300-second visibility lease. Mount its SQLite cache on persistent storage. The cache binds a source ID to a request digest and validated result, so redelivery after publication failure or process restart does not repeat extraction; conflicting reuse of a source ID fails. This is a single-consumer teaching adapter, not a distributed lock across replicas.

The consumer sends the result before deleting the input. Failure leaves the input available for redelivery. Results are **at-least-once**: a crash between successful publication and acknowledgement can republish a cached result, so downstream consumers must deduplicate by source ID. Malformed requests and exhausted extraction failures remain unacknowledged for configured DLQ handling. HTTP extraction does not use the queue cache.

## Verification

The complete project suite passed 117 tests after this extension. New tests cover transient/permanent retry classification, bounded jitter, original exception identity, one repair and loud exhaustion, durable cached redelivery, source-ID conflicts, publication-before-acknowledgement, and the shared HTTP/queue extraction boundary. Live fixture results are recorded separately in `deploy/lesson14/evidence/vendor-live-verification.json`.
