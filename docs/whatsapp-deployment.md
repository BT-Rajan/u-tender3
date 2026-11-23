# WhatsApp integration: deployment, configuration, migrations, rollback

## Status: not production-ready

The integration is built and tested in software. It has **not** been run against Meta with real test numbers, because no Meta credentials were available when this was built. Until the blocking items below are closed, WhatsApp stays disabled in production (`WHATSAPP_ENABLED=false`). The existing web application and admin dashboard are unaffected by this work and remain the production path.

### Blocking items

1. **Live Meta test.** Run the scenario list in section 6 against a real U-Tender test number and the U-Tender Meta app. Nothing has been sent through Meta yet.
2. **Templates approved in Meta.** Thirteen templates in English and Arabic (`backend/app/services/whatsapp_templates.py`). Until Meta approves each one, the outbox holds it. Nothing is sent. Approval lead time is often days.
3. **Flows published by Cogzi.** Run `utender:whatsapp:setup` (see section 3). The Flow IDs it prints go into `.env`.
4. **MySQL migration run.** Migrations 0007 to 0011 have only been run against SQLite. Run them against a MySQL copy of production first (section 4).
5. **Upload-link tokens in access logs.** Upload URLs carry the token in the path, so the web server's access log records it. Scrub `/upload/` from access logs before production, or move the token out of the path.
6. **Retention job not built.** `WHATSAPP_MESSAGE_RETENTION_DAYS` is read but nothing deletes old `whatsapp_message_events` or expired `document_upload_links` yet. Add a scheduled purge before production.
7. **Cogzi legacy tables.** Confirm whether `utender_*` tables or `storage/app/utender-documents` exist in any Cogzi environment (section 3). Purge or export them if so.

### Non-blocking, to schedule

- No rate limiting on the webhook, the upload pages, or login (login was already unlimited).
- No opt-out (STOP) handling and no quick-reply buttons on notifications.
- Publishing a broad tender fans out notifications inside the request. Move to the worker at scale.
- Drawing uploads and downloads stay on the web. WhatsApp shows names only, and contractors get signed links.

## 1. Architecture

- Meta calls U-Tender directly: the webhook at `/whatsapp/webhook` and the Flow data endpoint at `/whatsapp/flows`.
- U-Tender owns every operational record: identities, sessions, message events, outbox, documents, tenders, offers, notifications, and the Flow private key.
- Cogzi is used for one setup step: creating and publishing Flows in U-Tender's WABA. It is not in the runtime path and stores nothing for U-Tender. See `cogzi/docs/utender-integration.md`.

## 2. Environment variables

Set these in `backend/.env` (or the platform's secret store). Secrets must not be committed.

### Required in production

| Variable | Purpose |
|---|---|
| `APP_ENV` | `production`. Enables the startup check that refuses default secrets. |
| `DATABASE_URL` | MySQL connection string |
| `JWT_SECRET` | Must not be `change-me-in-production` |
| `STORAGE_SIGNING_SECRET` | Must not be the default |
| `CRON_SECRET` | Bearer secret for `/cron/*` |
| `API_URL` | Public HTTPS origin of the backend. Upload links and signed URLs are built from it. |
| `APP_URL` | Frontend origin |
| `CORS_ORIGINS` | Frontend origins |

### WhatsApp

| Variable | Default | Purpose |
|---|---|---|
| `WHATSAPP_ENABLED` | `false` | Master switch. `false` disables the webhook, Flow endpoint, and outbox dispatch. |
| `WHATSAPP_APP_SECRET` | none | U-Tender's Meta app secret. Signs webhook and Flow requests. |
| `WHATSAPP_VERIFY_TOKEN` | none | Subscription handshake token |
| `WHATSAPP_ACCESS_TOKEN` | none | System-user token for U-Tender's WABA |
| `WHATSAPP_PHONE_NUMBER_ID` | none | Sending number ID |
| `WHATSAPP_API_VERSION` | `v21.0` | Graph API version |
| `WHATSAPP_API_URL` | `https://graph.facebook.com` | Graph base URL |
| `WHATSAPP_FLOW_PRIVATE_KEY` | none | PEM private key matching the public key registered by the Cogzi setup. Never leaves U-Tender. |
| `WHATSAPP_FLOW_ID_REGISTRATION` | none | Printed by the Cogzi setup |
| `WHATSAPP_FLOW_ID_OWNER_DASHBOARD` | none | Printed by the Cogzi setup |
| `WHATSAPP_FLOW_ID_CONTRACTOR_DASHBOARD` | none | Printed by the Cogzi setup |
| `WHATSAPP_REQUIRE_APPROVED_TEMPLATES` | `true` | Hold templates until Meta approves them. Keep `true` in production. |
| `WHATSAPP_TEMPLATE_DOCUMENT_APPROVED` | `document_approved` | Template name |
| `WHATSAPP_TEMPLATE_DOCUMENT_REJECTED` | `document_rejected` | Template name |
| `WHATSAPP_OUTBOX_MAX_ATTEMPTS` | `8` | Retries before a message is dead-lettered |
| `WHATSAPP_MESSAGE_RETENTION_DAYS` | `30` | Read, but no purge job exists yet (blocking item 6) |

### Documents and upload links

| Variable | Default | Purpose |
|---|---|---|
| `DOCUMENT_MAX_MB` | `10` | Per-file limit for web and WhatsApp uploads |
| `UPLOAD_LINK_TTL_MINUTES` | `20` | Upload link lifetime |
| `UPLOAD_LINK_MAX_WRONG_CODES` | `5` | Wrong codes before a link is revoked |
| `MAX_UPLOAD_MB` | `50` | Request body cap (existing) |

### Tenders

| Variable | Default | Purpose |
|---|---|---|
| `TENDER_TIMEZONE` | `Asia/Kuwait` | Owners type deadlines in this zone. The database stores UTC. |

### Cogzi setup only (not set on U-Tender's server)

`UTENDER_WABA_ID`, `UTENDER_PHONE_NUMBER_ID`, `UTENDER_META_APP_ID`, `UTENDER_WHATSAPP_ACCESS_TOKEN`, `UTENDER_FLOW_ENDPOINT_URL`, `UTENDER_FLOW_PUBLIC_KEY_PATH`, `UTENDER_FLOWS_PATH`, and Cogzi's own `WHATSAPP_APP_ID`.

## 3. Setup sequence

1. **Meta.** Create U-Tender's own Meta app, separate from Cogzi's. Add the WhatsApp product. Attach the WABA and number. Note the app ID and secret.
2. **Keys.** Generate U-Tender's Flow key pair. Keep the private key in U-Tender's secret store (`WHATSAPP_FLOW_PRIVATE_KEY`). Give only the public key to Cogzi.
3. **Flows (Cogzi).** In Cogzi's environment, set the `UTENDER_*` variables and run:
   ```bash
   php artisan utender:whatsapp:setup            # dry run
   php artisan utender:whatsapp:setup --apply    # create, upload, point, connect, publish
   ```
   Before `--apply`, confirm Cogzi's app is **not** subscribed to U-Tender's WABA. The command checks this and refuses otherwise.
4. **Legacy check.** Confirm whether any Cogzi environment has `utender_*` tables or `storage/app/utender-documents` (blocking item 7).
5. **Webhook.** In U-Tender's Meta app, set the callback to `https://<API_URL>/whatsapp/webhook` with the verify token. Subscribe to the `messages` and `message_template_status_update` fields.
6. **Templates.** Create the thirteen templates from `whatsapp_templates.py` in both English and Arabic, under the same names, with the parameter counts shown. Wait for approval.
7. **Enable.** Set `WHATSAPP_ENABLED=true` and the Flow IDs. Deploy.
8. **Cron.** Run `GET /cron/whatsapp-outbox` every minute with `Authorization: Bearer $CRON_SECRET`. Run `GET /cron/deadline-reminders` hourly, as before.

## 4. Database migrations

Run in order. Each is additive except where noted.

| Revision | What it does | Notes |
|---|---|---|
| 0001–0006 | Existing schema | Unchanged |
| 0007 | `whatsapp_identities`, `whatsapp_message_events`, `whatsapp_flow_sessions`, `whatsapp_outbox` | Additive |
| 0008 | `users.email` and `users.password_hash` become nullable. `whatsapp_identities.user_id` becomes unique. | Existing web accounts unaffected. Downgrade fails if WhatsApp-only accounts exist. |
| 0009 | `document_upload_links`, `document_versions` | Additive |
| 0010 | `projects.bid_deadline` becomes nullable | Drafts. Downgrade fails if drafts without a deadline exist. |
| 0011 | Widens the `notifications.type` ENUM (MySQL). Adds `whatsapp_template_status`. | Downgrade fails on MySQL if rows use the new types. |

Commands:

```bash
cd backend
alembic upgrade head        # apply
alembic current             # confirm 0011
```

Test on a MySQL copy before production. The migration tests in this repo use SQLite, and migrations 0003, 0005 and 0006 use MySQL-only DDL that SQLite can't run.

## 5. Rollback

Roll back in this order, most conservative first.

1. **Stop traffic.** Set `WHATSAPP_ENABLED=false` and redeploy. The webhook and Flow endpoint return 404, and the outbox stops dispatching. Web and admin are unaffected.
2. **Stop Flows.** Deprecate the three Flows in Meta, or unset `WHATSAPP_FLOW_ID_*`. Users then get a text fallback.
3. **Stop templates.** Pause the templates in Meta.
4. **Code rollback.** Redeploy the previous release. Migrations 0007 to 0011 are backward-compatible with the previous code, so the schema can stay.
5. **Schema rollback (only if required).** `alembic downgrade 0006`. This deletes WhatsApp operational history and fails if WhatsApp-only accounts or drafts without deadlines exist. Take a database backup first. Migration 0011 on MySQL also fails while notifications use the new types.

Cogzi rollback: deprecate the Flows, as in step 2. Cogzi stores nothing else for U-Tender.

## 6. Test results

### Scenario coverage

Each scenario has automated tests that run the real endpoints. The journey test (`tests/test_phase8_journeys.py`) runs the full sequence in one pass.

| Scenario | Where it is tested |
|---|---|
| New owner registration | `test_registration_flow`, `test_whatsapp_end_to_end`, journey step 1 |
| New contractor registration | `test_registration_flow`, `test_whatsapp_end_to_end`, journey step 5 |
| Returning owner | `test_whatsapp_routing`, journey step 2 |
| Returning contractor | `test_whatsapp_routing`, `test_contractor_flows` |
| Interrupted registration and resume | `test_whatsapp_routing`, `test_whatsapp_end_to_end` |
| Document upload and replacement | `test_upload_links`, `test_document_checklist`, journey step 3 |
| Owner tender creation and amendment | `test_owner_flows`, `test_tender_service`, journey step 6 and 9 |
| Contractor project discovery | `test_contractor_flows` (browse, search, gates), journey step 7 |
| Offer submission and revision | `test_contractor_flows`, `test_tender_service`, journey step 7 |
| Sealed-bid confidentiality | `test_owner_flows`, `test_tender_service`, `test_whatsapp_notifications`, journey step 8 |
| Admin document approval | `test_document_checklist`, journey step 4 |
| WhatsApp notifications | `test_whatsapp_notifications` (80 tests), journey steps 6, 7, 9, 13 |
| Duplicate webhook delivery | `test_whatsapp_webhook`, `test_whatsapp_end_to_end`, journey step 11 |
| Invalid signatures | `test_whatsapp_webhook`, `test_whatsapp_signature`, journey step 12 |
| Expired upload links | `test_upload_links`, journey step 14 |
| Suspended users | `test_contractor_flows`, `test_upload_links`, journey step 13 |

### Suite results

| Suite | Result |
|---|---|
| U-Tender backend (`pytest`) | **496 passed** |
| Cogzi setup (`UtenderWhatsappSetupTest`) | **13 passed** |
| Cogzi Flow subset (`--filter=Flow`) | **339 passed** |
| Cogzi full suite | **1273 passed, 1 skipped** |

Cogzi's frontend had to be built (`npm run build`) before the Inertia page tests could run. That is an environment step, not a code change.

### Not tested

- Live Meta traffic, real test numbers, real template delivery, real Flow rendering on a phone.
- MySQL behaviour (the test database is SQLite).
- Load and fan-out at scale.

## 7. Verification

- **No business data in Cogzi.** The setup command writes no rows. Its tests check that the Cogzi stores for webhooks, Flow submissions, drafts, sessions, keys, and chats stay empty after `--apply`. The inventory of existing Cogzi stores and how each is bypassed is in `cogzi/docs/utender-integration.md`.
- **All operational data in U-Tender.** Identities, sessions, message events, outbox, documents, tenders, offers, notices, and the Flow private key are all U-Tender tables. U-Tender's runtime code makes no Cogzi call. The only Cogzi mentions in U-Tender are comments about its setup role.
- **Existing web application and admin dashboard.** Every pre-existing test still passes (the suite now totals 496). The web lifecycle, offer, visibility and upload routes now call shared services, and their responses are unchanged. Two web tests were changed because they uploaded placeholder bytes that the new file rule correctly refuses.
- **Permissions and business rules.** Preserved and tested: verification gate, payment gate, sealed-bid rules, ownership checks, drawing visibility, the lifecycle state machine, amendment records, offer revisions and withdrawal.
