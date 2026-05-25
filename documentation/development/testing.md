# Testing

Run all tests:

```bash
go test ./...
```

Run the repo wrapper:

```bash
bash run_tests.sh --unit
bash run_tests.sh --integration
bash run_tests.sh --coverage
```

Integration tests use fake provider servers through provider base URL overrides, so they do not require live provider credentials.

Before opening a PR, run:

```bash
gofmt -w cmd internal
go test ./...
bash run_tests.sh --unit
bash run_tests.sh --integration
docker build -t sentinelrouter-go-smoke .
```

