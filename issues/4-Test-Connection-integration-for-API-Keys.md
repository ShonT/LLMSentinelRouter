# "Test Connection" integration for API Keys

## The Issue
Users currently have no way to verify that an API key they’ve entered is valid before saving it to the configuration. This leads to runtime failures and manual debugging.

## Why It's Critical
Invalid keys cause request failures, obscure error messages, and degrade the user experience. A quick validation step before persistence prevents misconfiguration and reduces support overhead.

## Proposed Fix
Add a "Test" button next to each unobfuscated key in the dashboard’s API‑Keys section. Clicking this button triggers a lightweight ping (e.g., a dummy call to `/models`) to verify the key is valid before the user saves the config.

## Implementation Details
1. **Backend Validation Endpoint** – Create a new endpoint (e.g., `POST /admin/config/test-key`) that accepts a provider name and key, performs a minimal API call (e.g., list models or a simple health check), and returns `{ "valid": true/false, "message": "..." }`.
2. **Frontend UI Integration** – In the API‑Keys table, add a "Test" button (icon: &#x1F50C;) next to each editable key field. On click, the button sends the current key value to the validation endpoint and shows a spinner.
3. **Visual Feedback** – On success, show a green checkmark and a brief "Key valid" toast. On failure, show a red X with the error reason (e.g., "Invalid key" or "Network error").
4. **Non‑Blocking** – The test should be asynchronous and not block other UI operations. Invalid keys can still be saved (if the user chooses to), but the UI should warn clearly.
5. **Caching** – Consider caching successful test results for a short time to avoid repeated calls while the user is editing.

## Example Workflow
1. User types `sk-...` into the OpenAI key field.
2. Clicks the "Test" button.
3. Dashboard sends `{ "provider": "openai", "key": "sk-..." }` to `/admin/config/test-key`.
4. Backend makes a HEAD or GET request to `https://api.openai.com/v1/models` with the key.
5. Returns `200 OK` → UI shows "Key valid".
6. Returns `401 Unauthorized` → UI shows "Invalid key – check your credentials".

## Related Components
- `sentinelrouter/server.py` (new endpoint)
- `sentinelrouter/clients.py` (provider‑specific test logic)
- `sentinelrouter/dashboard.py` (UI button and event handling)
- `sentinelrouter/config.py` (optional caching)

## Security Considerations
- Test requests must not log the full key in plaintext.
- Limit test frequency to prevent abuse (rate‑limit per IP).
- Ensure the test endpoint is only accessible from authenticated/admin sessions.

## Priority
Medium – improves configuration ergonomics and reduces misconfiguration.