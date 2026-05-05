# Cited — Replit Project

ATS scoring tool for South African job seekers. Free scan → R99 diagnostic
report → R450+ rewrite. CareerForge sub-brand.

## Project layout

```
cited/
├── main.py                  ← FastAPI entry point
├── pyproject.toml           ← Python dependencies
├── .replit                  ← Replit run + deploy config
├── .env.example             ← Copy to .env (or set in Replit Secrets)
├── app/
│   ├── routes/
│   │   ├── scan.py          ← /api/scan/free  (Tier 1 free scan)
│   │   ├── payment.py       ← /api/payment/checkout/{tier}  (PayFast redirect)
│   │   ├── webhook.py       ← /api/webhook/payfast  (PayFast ITN, audit-logged)
│   │   └── upgrade.py       ← /upgrade flow (selection + report + rewrite intake)
│   ├── scoring/             ← Heuristic ATS scoring engine (see below)
│   ├── scorer.py            ← Backwards-compat shim → app/scoring/
│   ├── parsers.py           ← PDF + DOCX text extraction
│   ├── models.py            ← Pydantic types
│   ├── db.py                ← SQLite persistence (scans, rewrite_intake, payments)
│   └── templating.py        ← Shared Jinja templates instance
├── templates/
│   ├── base.html            ← Shared chrome (head, masthead, footer)
│   ├── index.html           ← Landing page
│   ├── upgrade.html         ← Tier 2/3 selection
│   ├── upgrade_unlocked.html ← Tier 2 detailed report (the R99 deliverable)
│   ├── upgrade_rewrite.html ← Tier 3 intake form
│   ├── upgrade_return.html  ← Post-payment redirect target
│   ├── upgrade_cancel.html  ← Cancelled-payment soft landing
│   └── upgrade_not_found.html ← 404 for invalid scan IDs
├── static/
│   ├── styles.css
│   └── app.js
└── data/                    ← SQLite DB (gitignored)
```

## The scoring engine

The scorer is heuristic-only — no LLM calls, no per-scan API costs. The total
out of 100 is a weighted sum of four components:

| Component       | Weight | What it measures                                  |
|-----------------|--------|---------------------------------------------------|
| Parseability    | 40%    | Can an ATS parser actually read this file?        |
| Structure       | 20%    | Sections, contact details, dates, region format   |
| Keyword fit     | 25%    | Match against job ad (or industry baseline)       |
| Content quality | 15%    | Bullets, action verbs, quantified achievements    |

**Calibration commitments:**
- A clean CV without a job ad lands ~70-85
- A clean CV with a matching job ad can hit 90-96 (96 is the cap)
- Below 50 is reserved for CVs with real structural problems
- Above 95 is essentially impossible — there's always something to improve

This is a deliberate honesty principle: most online ATS scorers exist to sell
rewrites, so they're rigged to score everyone low. Cited does the opposite —
honest scores build trust faster than fake low scores do.

**Regional profiles** (ZA / UK / US) are not cosmetic. Each profile changes:
phone-number patterns, location markers, document term ("CV" vs "Résumé"),
expected length, date format, and region-specific certifications.

**To upgrade to LLM-enhanced scoring later:** the seam is `app/scoring/keywords.py`.
The `_extract_keywords_from_job_ad()` function can be swapped for a Claude API
call when the funnel converts and per-scan cost is justified.

## Day 0: from clone to local

1. Import this folder into a new Replit project (or push to GitHub then
   "Import from GitHub" in Replit).
2. Replit will auto-detect the `pyproject.toml` and install dependencies.
3. Open Tools → Secrets in the Replit sidebar and add at minimum:
   - `ANTHROPIC_API_KEY` — for the scorer's keyword extraction
4. Click Run. You should see uvicorn boot and a webview load the landing page.
5. Try the free scan with any CV PDF or DOCX. You'll see the score panel
   render in place of the form.

If you skip the `ANTHROPIC_API_KEY` it still runs — the scorer falls back to
a naive bag-of-words approach for keyword extraction.

## Day 1: deploy to cited.co.za

The .replit config sets `deploymentTarget = "autoscale"` so Replit will
suggest Autoscale Deployment when you click Publish.

1. **Click Publish** (top-right in Replit).
2. **Choose Autoscale Deployment**. Default machine config is fine.
3. **Wait for deploy.** You'll get a `*.replit.app` URL.
4. **Test the deployed URL.** Run a scan on the .replit.app subdomain to
   confirm everything works in the deployment environment.
5. **Link the custom domain.** Deployments → Settings → Link a domain →
   enter `cited.co.za`. Copy the A and TXT records Replit shows you.
6. **At your domain registrar**, add those A and TXT records. Wait for DNS
   propagation (usually 15 min – 2 hours, occasionally up to 48).
7. **Replit auto-provisions TLS.** Once propagation completes, the lock icon
   appears on https://cited.co.za. No manual SSL work.
8. **Update PUBLIC_BASE_URL** in Replit Secrets to `https://cited.co.za` so
   PayFast redirects come back to the right place.

## Adding payments (Tier 2 R99 + Tier 3 R450)

The PayFast integration is scaffolded but not enabled by default — you need
to add the merchant credentials.

1. Sign up at payfast.io (already in Andrew's stack).
2. Get your sandbox credentials first (PayFast provides test credentials).
3. Add to Replit Secrets:
   - `PAYFAST_MERCHANT_ID`
   - `PAYFAST_MERCHANT_KEY`
   - `PAYFAST_PASSPHRASE` (only if recurring billing is enabled on your account; for one-off payments leave empty)
   - `PAYFAST_SANDBOX=true`
   - `PUBLIC_BASE_URL=https://cited.co.za` (or your *.replit.app URL during testing)
4. Test the full flow end-to-end with sandbox cards.
5. When confident, switch sandbox credentials for live ones and set
   `PAYFAST_SANDBOX=false`.

## The full upgrade flow (now built)

```
Free scan       →  /api/scan/free                 (Tier 1 — score on screen)
   ↓
Click upgrade   →  /upgrade?scan={id}             (Tier 2 vs Tier 3 selection)
   ↓
Click checkout  →  /api/payment/checkout/{tier}   (returns PayFast redirect URL)
   ↓
PayFast hosted checkout                           (user pays)
   ↓
Two things happen in parallel:
  - User redirected to /upgrade/return            (polls for ITN confirmation)
  - PayFast POSTs ITN to /api/webhook/payfast     (verifies + unlocks tier)
   ↓
Once tier upgraded:
  - Tier 2  → /upgrade/report                     (full diagnostic report)
  - Tier 3  → /upgrade  (renders intake form)     (rewrite intake)
              ↓
              POST /upgrade/rewrite                (intake stored, manual rewrite begins)
```

Every PayFast ITN — successful or rejected — is logged to the `payments` table
for audit/debugging. Look at `data/cited.db` with any SQLite browser to see
the trail.

## What's not built yet

- POPIA / Privacy / Terms static pages (footer links currently 404)
- Rate limiting (consider adding slowapi if abuse becomes an issue)
- Proper logging (currently just print statements — fine for dev)
- Operator notification on Tier 3 payment (currently just a print to logs;
  check `data/cited.db` `rewrite_intake` table for new submissions)
- Email delivery of any kind. Deliberately dropped for v1 — results live
  on-screen + recoverable via the saved scan URL. If/when a paid-tier
  upsell sequence justifies it, transactional service (e.g. Resend) goes
  here, not a newsletter platform.

These are intentional v1 omissions. The full payment flow is end-to-end functional;
these are polish items for Day 30+.

## Running locally without Replit

```bash
pip install -e .
cp .env.example .env
# edit .env with your keys
python main.py
```

Visit http://localhost:8000.

## Cost expectations

- **Replit Autoscale free tier:** Fine for development and the first weeks
  of low traffic. Scales to zero when idle (cold starts ~5–10s).
- **Replit Core:** Roughly $20/month, gets you better autoscale defaults and
  the "Made with Replit" badge removed.
- **Reserved VM:** $7+/month if cold starts hurt conversion enough to
  justify always-on. Probably worth it once you're getting >50 scans/day.
- **Anthropic API:** Currently $0 — the heuristic scorer doesn't use Claude.
  Future LLM-enhanced Tier 2 would run ~$0.003 per scan.
- **Domain:** ~R250/year (already purchased).

Total at launch: ~$0–$10/month. At 1000 scans/month: ~$15–$30/month.

## Kill criterion

Per Playbook v6.1: 5 paying customers (Tier 2 R99 OR Tier 3 R450) by Day 90,
or CareerForge/Cited gets parked. The SQLite database makes this trivial to
measure — count rows where `tier > 1`.
