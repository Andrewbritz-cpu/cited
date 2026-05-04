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
│   │   └── webhook.py       ← /api/webhook/payfast  (PayFast ITN)
│   ├── scorer.py            ← ★ Plug your existing ATS scoring tool in here
│   ├── parsers.py           ← PDF + DOCX text extraction
│   ├── models.py            ← Pydantic types
│   ├── db.py                ← SQLite persistence
│   └── email.py             ← Buttondown integration
├── templates/
│   └── index.html           ← Landing page (Jinja2)
├── static/
│   ├── styles.css
│   └── app.js               ← Form submission, FAQ, scanner animation
└── data/                    ← SQLite DB lives here (gitignored)
```

## The seam to know about

`app/scorer.py` is the one file you'll modify to plug in your existing v3
ATS scoring tool with ZA/UK/US regional profiles. The function signature is:

```python
def score_cv(
    cv_text: str,
    job_description: str = "",
    region: str = "auto",
) -> ScoringResult:
    ...
```

Everything else in the codebase only depends on the `ScoringResult` shape
defined in `app/models.py`. Replace the body of `score_cv()` with a call into
your scorer and the rest works without modification.

The placeholder implementation in this repo uses simple heuristics + a Claude
API call for keyword extraction. It's good enough to test the full end-to-end
flow before you wire your real scorer in, but the score numbers it produces
are illustrative only.

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
   - `PAYFAST_PASSPHRASE`
   - `PAYFAST_SANDBOX=true`
4. Test the full flow end-to-end with sandbox cards.
5. When confident, switch sandbox credentials for live ones and set
   `PAYFAST_SANDBOX=false`.

The frontend doesn't currently render the upgrade page itself — `/upgrade`
will 404 until you build it. The scaffolding is all server-side; you need a
small `templates/upgrade.html` and a route that calls
`POST /api/payment/checkout/diagnostic` to get the redirect URL.

## What's not built yet

- `/upgrade` page (Tier 2 unlock UI after free scan)
- `/upgrade/return` and `/upgrade/cancel` redirect handlers
- The Tier 2 detailed report rendering (full annotations + DIY guide)
- The Tier 3 rewrite intake flow (Google Form alternative inside the app)
- POPIA / Privacy / Terms static pages (footer links currently 404)
- Rate limiting (consider adding slowapi if abuse becomes an issue)
- Proper logging (currently just print statements)

These are deliberate omissions for the v1 launch. The free-scan loop is the
critical path — get that working and converting before building anything else.

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
- **Anthropic API:** ~$0.003 per scan with the current Claude Sonnet
  keyword extraction call. 1000 free scans/month = ~$3.
- **Buttondown:** Free tier covers up to 100 subscribers, $9/month after.
- **Domain:** ~R250/year (already purchased).

Total at launch: ~$0–$10/month. At 1000 scans/month: ~$15–$30/month.

## Kill criterion

Per Playbook v6.1: 5 paying customers (Tier 2 R99 OR Tier 3 R450) by Day 90,
or CareerForge/Cited gets parked. The SQLite database makes this trivial to
measure — count rows where `tier > 1`.
