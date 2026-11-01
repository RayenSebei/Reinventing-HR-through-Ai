# n8n verification against the official repository (rule R25)

Source checked: `github.com/n8n-io/n8n` at commit `c44bd78f3834fb4e5a14cdcee96d552a9c4e4e92` (2026-10-31), package `n8n` version 2.46.0. Files read: `packages/nodes-base/nodes/{Webhook,Crypto,If,EmailSend,RespondToWebhook,Transform/RemoveDuplicates}`, `packages/workflow/src/interfaces.ts`.

| Node in `n8n/vouch-deliver.workflow.json` | Type | typeVersion used | Versions in source |
|---|---|---|---|
| Webhook from Vouch gateway | `n8n-nodes-base.webhook` | 2 | 1, 1.1, 2, 2.1, 2.2 |
| HMAC-SHA256 of payload / of computed signature / of received signature | `n8n-nodes-base.crypto` | 2 | 1, 2 |
| Signature valid? | `n8n-nodes-base.if` | 2.2 | 1, 2, 2.1, 2.2, 2.3, 2.4 |
| Send email (sandbox SMTP) | `n8n-nodes-base.emailSend` | 2.1 | 1, 2, 2.1 |
| Reply: delivered / rejected | `n8n-nodes-base.respondToWebhook` | 1.1 | 1 … 1.5 |

## Facts that changed the design
1. **Send Email appends text by default.** `EmailSend/v2/send.operation.ts`: if `options.appendAttribution` is undefined and `nodeVersion >= 2.1`, it appends "This email was sent automatically with n8n" and a link. The workflow had `options: {}` at 2.1, so every approved email would have carried text the manager never approved. **Fixed:** `appendAttribution: false`, enforced by `test_n8n_does_not_append_text_the_manager_never_approved`.
2. **No built-in HMAC check on the Webhook node.** `Webhook/description.ts` offers `basicAuth`, `headerAuth`, `jwtAuth`, `none`. The HMAC check is built from Crypto nodes.
3. **The If node's string equality is not constant-time.** The workflow now compares `HMAC(secret, computed_signature)` with `HMAC(secret, received_header)` (double HMAC), so timing reveals nothing about the real signature. Uses only Crypto + If, no Code node. A missing header becomes an empty string and fails the comparison.
4. **Crypto v2 keeps the incoming fields** (`{ ...item.json }` then sets `dataPropertyName`), so headers and body survive the three HMAC steps.
5. **`toEmail` is passed through as a string**, and CC/BCC/Reply-To are options. Vouch guarantees one clean address; the workflow has no CC/BCC (lint test).
6. **Send Email cannot set `In-Reply-To`/`References`** (no such option). Reply matching must use a signed token (master plan AX-04).
7. **Not used: Remove Duplicates.** It exists (`removeItemsSeenInPreviousExecutions`, "Value Is New"), but when it drops a duplicate the workflow produces no item, and what the webhook (`responseMode: responseNode`) then answers is not defined in the code read. Vouch's own rule (never re-send a `DELIVERED` row) is the guarantee instead; see RESIDUAL_RISK.md.

## Still to do on a real n8n (cannot run here)
Import the workflow once on the n8n version you pin, set the Crypto credential's Hmac Secret (≥ 32 characters, same as `VOUCH_N8N_HMAC_SECRET`) on all three Crypto nodes, then: a correct signature → 200 and one email in Mailpit without the attribution line; a wrong or missing `X-Vouch-Signature` → 401 and nothing sent.
