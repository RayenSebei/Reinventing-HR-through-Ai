# n8n: deliver approved actions

`vouch-deliver.workflow.json` is the only path from Vouch to a real inbox. **n8n sits behind the Action Gateway.** It only receives actions that a manager already approved, and it checks Vouch's signature before sending anything.

```
Vouch gateway ──POST (signed)──► Webhook ─► Crypto: HMAC of payload_json
                                         ─► Crypto: HMAC of that signature ─► Crypto: HMAC of the received signature
                                         ─► If: the two second-level HMACs match?
                                               yes ─► Send Email (no n8n attribution) ─► reply 200
                                               no  ─► reply 401 (nothing sent)
```

All nodes come from the official n8n repository (`packages/nodes-base`), re-checked against commit `c44bd78` (n8n 2.46.0) on 2026-11-01; details in `docs/plan/N8N_VERIFICATION.md`:

| Node | Type | typeVersion |
|---|---|---|
| Webhook | `n8n-nodes-base.webhook` | 2 |
| Crypto (action: Hmac) | `n8n-nodes-base.crypto` | 2 |
| If | `n8n-nodes-base.if` | 2.2 |
| Send Email | `n8n-nodes-base.emailSend` | 2.1 |
| Respond to Webhook | `n8n-nodes-base.respondToWebhook` | 1.1 |

## Set it up

1. **Start n8n:** `npx n8n`, or `docker run -it --rm -p 5678:5678 docker.n8n.io/n8nio/n8n`.
2. **Start a sandbox inbox** so no real email is ever sent, for example Mailpit: `docker run -p 8025:8025 -p 1025:1025 axllent/mailpit` (web inbox at http://localhost:8025).
3. In n8n: **Workflows → Import from file →** `vouch-deliver.workflow.json`.
4. Create two credentials in n8n and select them on the nodes:
   - **Crypto** credential (used by all three HMAC nodes): set **Hmac Secret** to a random string of at least 32 characters.
   - **SMTP** credential (used by "Send email"): host `localhost`, port `1025`, no TLS, no auth (Mailpit).
5. **Activate** the workflow. Copy its production URL, e.g. `http://localhost:5678/webhook/vouch-deliver`.
6. Start Vouch with the same secret:
   ```bash
   VOUCH_OUTBOUND_MODE=live \
   VOUCH_N8N_WEBHOOK_URL=http://localhost:5678/webhook/vouch-deliver \
   VOUCH_N8N_HMAC_SECRET=<the same Hmac Secret> \
   python -m app --seed          # prints a one-time password (VOUCH_DEMO_MODE=1 is refused with live)
   ```
7. Approve and send an invite in Vouch. It appears in Mailpit, and the Vouch outbox shows `DELIVERED`.

**Security check to show the judges:** send the webhook a request with a wrong `X-Vouch-Signature`. n8n answers 401 and sends nothing.

## What was tested

Vouch's signing was tested against a stand-in receiver that applies the same rule (HMAC-SHA256, hex, over the `payload_json` string, compared with the `X-Vouch-Signature` header): the outbox showed `DELIVERED`. n8n itself could not be installed in the environment where this was built, so **import and run the workflow once on a real n8n before the demo.**

## Rules

- n8n never calls Vouch's execute endpoint, and never approves anything.
- Don't add AI Agent nodes with tools to this path.
- The If node's equality test is not constant-time, so it never compares the raw signature: it compares HMACs of the two signatures (double HMAC), which reveals nothing useful through timing. Keep n8n on a private network anyway.
- The Send Email node (typeVersion 2.1) adds an "automatically sent with n8n" line unless `appendAttribution` is false. It is set to false so the email is exactly what the manager approved; a test enforces it.
- No CC/BCC on the Send Email node (a test enforces it). The recipient is the address a recruiter confirmed in Vouch.

## Ideas for later (not built)

- **Inbox digest:** Email Trigger (IMAP) → group by type → post a summary to Vouch.
- **Follow-up reminders:** Schedule Trigger → ask Vouch for candidates with no reply → Vouch creates *draft* proposals that still need a manager's approval.
