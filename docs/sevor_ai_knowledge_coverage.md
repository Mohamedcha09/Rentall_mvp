# Sevor AI knowledge coverage

## Approved, source-backed coverage

The following customer-support areas have source-backed entries in
`app/chatbot/approved_knowledge.json`:

| Area | Supported examples | Primary inspected source |
| --- | --- | --- |
| Account access | login, password reset email/link, changing a password, email verification | `app/auth.py` |
| Verification status | separate email activation, account status, and document-review status for the current user | `User`, `Document`, `app/auth.py`, `app/admin.py` |
| Listings | create/edit, validation, and visibility/review states | `app/items.py`, `app/admin_items.py` |
| Bookings | dates, request/decision state, pending owner response, pickup/return proof | `app/routes_bookings.py`, `app/routes_deposits.py` |
| Payments and deposits | booking payment status, the PayPal sequence, and stored deposit state | `Booking`, `app/pay_api.py`, `app/routes_deposits.py` |
| Owner payouts | settings and current-user booking payout state | `app/payout_settings.py`, `Booking` |
| Region | saved display-currency preference and deliberate dismissal of the region picker | `app/routes_geo.py` |
| Messages | starting a conversation and existing image/file/voice behavior | `app/messages.py`, `app/message_attachments.py` |
| Favorites, reviews, reports | existing routes and safe support escalation | `app/routes_favorites.py`, `app/reviews.py`, `app/reports.py` |

Current-user questions can additionally use bounded read-only tools for a
booking, owned listing, verification state, or eligible payout status. A tool
is not required for a general question and is not an authority to retrieve a
different user's data.

## Deliberately partial or unavailable

The bot must offer the known part, ask one focused question where useful, or
use the existing human handoff for the following until a policy owner approves
them:

- listing review time promise;
- refund eligibility and processing timeline;
- universal deposit formula or release timing;
- payout timing, fees, and guarantees;
- owner response-time guarantee and cancellation policy;
- public verification-document requirements and rejection catalogue;
- supported payment methods, universal fees, and tax rules;
- post-return report window and automatic-deposit-release wording;
- cash-payment support and rules;
- exact review availability after a return.

The last four contain a material mismatch between walkthrough copy and the
inspected operational routes. `knowledge_gaps.json` keeps the exact owner
questions and source list. They are intentionally not promoted to facts.

## Updating safely

1. Identify a public, approved policy or an operational behavior that the code
   actually proves.
2. Add or revise a compact entry with `id`, topic, answer, source, review state,
   and update information. Include symptoms, troubleshooting, clarification,
   related topics, and escalation rules where they improve safe routing.
3. Add an unresolved or conflicting policy to `knowledge_gaps.json` instead of
   improvising it in an answer.
4. Run the chatbot support, corpus, and runtime evaluation tests. Review
   provider-generated answers separately when a provider is configured.

Knowledge is server-side support material. It is not a replacement for the
existing human-support workflow or a source of private customer data.
