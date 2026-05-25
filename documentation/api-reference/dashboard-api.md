# Dashboard API

The dashboard is embedded in the Go binary and served from `/`.

Endpoints:

- `GET /api/dashboard/session-defaults`
- `POST /api/dashboard/session-defaults`
- `POST /api/dashboard/regenerate-session-id`
- `GET /api/dashboard/live`
- `GET /api/dashboard/metrics`
- `GET /api/dashboard/configuration`
- `GET /api/dashboard/logs`
- `DELETE /api/dashboard/logs`
- `POST /api/dashboard/model/{model_id}/reset-cost`
- `POST /api/dashboard/model/{model_id}/status`
- `POST /api/dashboard/reset-all-costs`
- `POST /api/dashboard/start-all`
- `POST /api/dashboard/stop-all`
- `POST /api/dashboard/models`
- `PUT /api/dashboard/models/{model_id}`
- `DELETE /api/dashboard/models/{model_id}`
- `PUT /api/dashboard/judge-config`
- `PUT /api/dashboard/routing-order`
- `GET /api/dashboard/full-config`

Model status changes are runtime controls. They do not rewrite `sentinel_config.json`; active status is enforced by the Go router while the process is running.

