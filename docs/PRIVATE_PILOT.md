# Private typing pilot

The owner signs in with a one-time work-email code and sees only their interviews. A successful typed turn is saved to Supabase Postgres before Birbal shows the reply. The pilot does not open voice calls or publish links, board entries, GitHub issues, or brief files on the server. Approving lets the owner download the redacted versions; the raw owner brief stays view-only in the app.

## Configure a separate deployment

1. Create a dedicated [Supabase project](https://supabase.com/dashboard/projects) for the pilot. In its SQL editor, apply [the migration](../supabase/migrations/20261123173000_private_pilot.sql). Start with an empty pilot: demo interviews intentionally have no inferred owner and are not imported.
2. In Auth, disable **Allow new users to sign up** and anonymous sign-ins. Add and confirm invited work-email accounts as an admin. Configure the [Magic Link email template](https://supabase.com/docs/guides/auth/auth-email-templates) to display the code `{{ .Token }}`, and configure [SMTP](https://supabase.com/docs/guides/auth/auth-smtp) to deliver to invitees. Supabase's default mail service may only reach project team addresses.
3. Use an [asymmetric Supabase JWT signing key](https://supabase.com/docs/guides/auth/signing-keys) (ES256 or RS256); legacy HS256 access tokens are not accepted. Set a short access-token lifetime. Birbal clears its cookie on sign-out and asks users to sign in again on expiry; it does not keep a refresh token.
4. Set the variables below in the pilot deployment's secret environment. Use the public HTTPS origin exactly as the browser displays it. Local HTTP is allowed only on loopback. Keep one app process/replica for the pilot.

   | Variable | Value |
   |---|---|
   | `BIRBAL_AUTH_MODE` | `pilot` |
   | `BIRBAL_APP_ORIGIN` | Birbal's own origin, e.g. `https://birbal.example.com` |
   | `SUPABASE_URL` | Supabase project origin |
   | `SUPABASE_PUBLISHABLE_KEY` | Project publishable key for sign-in |
   | `SUPABASE_KEY` | Server-only secret or legacy service-role key for storage |

5. Before inviting anyone, test with two approved accounts and fictional text. Confirm one cannot open the other's direct state/review/download URLs; restart the app and confirm the owner can resume. Try an unapproved email and confirm it cannot sign in. Verify the configured AI providers and retention policy before admitting any company data; interviews still go to the configured Talker and Scribe.

## Operational limits

- Writes do not fall back to local files. If the database becomes unavailable before committing a reply, keep the interview open: Birbal marks the pending save and retries it. Graceful shutdown makes a bounded attempt to save completed Scribe notes. Memory-only data is not guaranteed to survive a crash.
- A signed token remains valid until it expires. For urgent offboarding, remove access at the network perimeter or take the pilot offline while sessions expire; deleting a Supabase account also removes its persisted interviews. Add centrally enforced revocation and retention controls before a broader rollout.
- Use a separate Supabase project and host for the pilot. If you need to roll back, take the pilot offline or return to a known private build. Never switch its host to demo mode as a rollback.
