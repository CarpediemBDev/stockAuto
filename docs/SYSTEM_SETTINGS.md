# System Settings

`system_settings` stores service-wide runtime switches and policy values as a restricted key-value table.

This table is for global operational controls. User-specific trading mode, strategy, bot status, and Telegram chat linkage remain in `user_settings`. API keys, secrets, account numbers, and other credentials must not be stored in `system_settings`.

## Columns

- `key` (VARCHAR, PK): Setting key. Application code reads only keys defined in the system setting registry.
- `value` (TEXT): Serialized setting value.
- `value_type` (VARCHAR): One of `bool`, `int`, `float`, `string`, or `json`.
- `category` (VARCHAR, Index): Operational category such as `ai`, `scanner`, `trading`, `telegram`, or `maintenance`.
- `description` (TEXT, Nullable): Human-readable setting description.
- `is_runtime` (BOOLEAN): Whether the value can be applied without a server restart.
- `is_public` (BOOLEAN): Whether the value can be exposed to admin UI/API responses.
- `updated_by` (INTEGER, FK -> `users.id`, Nullable): Last admin user that changed the value.
- `created_at`, `updated_at` (DATETIME): Creation and update timestamps.

## Initial Setting

- `enable_gemini_news_analysis=false`

Gemini-backed scanner news analysis is disabled by default. When disabled or lookup fails, the scanner uses local news fallback analysis only.

## Admin Surface

- UI: `/admin` -> `전역 런타임 설정` tab
- List API: `GET /api/v1/admin/system-settings`
- Update API: `PATCH /api/v1/admin/system-settings/{key}` with `{ "value": ... }`

Only admin users can use the system settings API. Responses expose registered operational keys only. Secrets and user-specific settings are not part of this surface.

## Runtime Rules

- Secrets are never stored in this table.
- Unknown keys are rejected by the code registry.
- Invalid values fall back to the registry default.
- Runtime reads use a short TTL cache to avoid querying the database for every scanner candidate.
