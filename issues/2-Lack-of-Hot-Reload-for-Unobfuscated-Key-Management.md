# Lack of "Hot-Reload" for Unobfuscated Key Management

## The Issue
If keys are stored in a .env or static config file, the dashboard acts only as a viewer. To be truly functional for local dev, the dashboard needs a Stateful Configuration Manager that supports "Hot-Reload."

## Why It's Critical
Since you want keys to be visible and editable locally, the dashboard must have a direct write‑back mechanism to your local configuration. Without this, editing a key in the UI would require a manual server restart, defeating the purpose of a "live" dashboard.

## Proposed Fix
Add a "Live Edit" mode in the API Keys section that updates the router's memory‑resident config and persists it to disk immediately without dropping active connections.

## Implementation Details
1. Introduce a configuration‑manager service that watches the key‑storage file (e.g., `.env`, `config/models_config.json`) for changes and reloads them in‑memory.
2. Expose a secure PUT/PATCH endpoint (e.g., `/admin/config/keys`) that accepts key updates, validates them, writes them to the underlying file, and refreshes the in‑memory configuration of all connected router instances.
3. Ensure the update is atomic: write to a temporary file, then rename, to avoid corruption.
4. Add a UI toggle "Live Edit" that switches the API‑Keys table from read‑only to editable fields, with a "Save" button that calls the new endpoint.
5. Provide immediate visual feedback (success/error) and log the change for audit.

## Related Components
- `sentinelrouter/config.py`
- `sentinelrouter/state_manager.py`
- `sentinelrouter/dashboard.py` (UI)
- `sentinelrouter/server.py` (new admin endpoint)

## Security Considerations
- Only allow hot‑reload from trusted IPs (localhost) or when authentication is enabled.
- Validate new keys format before persisting (e.g., check length, prefix).
- Maintain a backup of the previous config for rollback.

## Priority
High – essential for a usable local‑development dashboard.