# Current Architecture Observations

Observations from black-box testing of Cynbit's public infrastructure, newsletter interface, and contact workflows.

---

### 1. Hosting Infrastructure & Edge Delivery Observations
- **Hosting Tier:** Web traffic terminates on the **Vercel** platform (`server: Vercel` response header).
- **Edge Caching:** Static and pre-rendered pages return `x-vercel-cache: HIT` and `Age` headers, demonstrating active edge CDN caching.
- **Compression:** Outbound responses use **Brotli** compression (`Content-Encoding: br`).
- **Conditional GET:** Navigation requests return `Cache-Control: public, max-age=0, must-revalidate` and `ETag`, generating standard `HTTP 304 Not Modified` on revalidation.
- **Application Framework:** Response headers and payload structures indicate a **Next.js** (App Router) deployment.

---

### 2. Contact Inquiries Workflow Observations
- **Endpoint:** `POST https://www.cynbit.in/contact`
- **Response Format:** Returns `HTTP 200 OK` with `Content-Type: text/x-component` and chunked body `1:{"success":true}`, characteristic of React Server Components (RSC) flight data.
- **Validation Behavior:**
  - Empty submissions are blocked by frontend validation.
  - Invalid email formats (`abc123`) are rejected.
  - Required text fields containing only whitespace characters (`name = "   "`, `message = "   "`) were accepted and triggered automated acknowledgement emails.
- **Architectural Nuance:** Receiving HTTP 200 alone indicates server action execution; it does not constitute proof that the inquiry was permanently committed to an internal database.

---

### 3. Newsletter Subscription Workflow Observations
- **Endpoint:** Public newsletter input form on `https://www.cynbit.in/`.
- **Initial Submission:** Submitting a newly controlled email address immediately dispatches a welcome email (`"Welcome to Cynbit"`).
- **Verification Loop:** The welcome email contained neither an email confirmation link nor an unsubscribe link (Single Opt-In behavior).
- **Duplicate Submission:** Submitting an already registered address returns `{"success": true, "message": "You're already in our intelligence network!"}`, indicating backend deduplication logic while enabling user enumeration.

---

### 4. Known vs. Inferred vs. Unverified Architecture Elements

| Architecture Element | Status | Technical Details |
| :--- | :--- | :--- |
| **Web / Edge Tier** | **Confirmed Observation** | Vercel Edge Network, Next.js App Router, Brotli compression |
| **Email Authentication** | **Confirmed Observation** | `SPF: PASS`, `DKIM: PASS`, `DMARC: PASS` (via `opportunities@cynbit.in`) |
| **Client-Side Storage** | **Confirmed Observation** | LocalStorage limited to `gcl_ls` and `cynbit_newsletter_seen` (no credentials) |
| **Database Tier** | **Reasonable Inference** | Decoupled external managed database (e.g., Supabase / Neon / AWS RDS) |
| **Transactional Mailer** | **Reasonable Inference** | Integrated commercial mail service (e.g. AWS SES / SendGrid / Resend) |
| **Database Backups & RPO** | **Unverified Unknown** | Snapshot schedules, retention windows, offsite replication unknown |
| **Multi-Region Failover** | **Unverified Unknown** | Secondary hosting, cold/warm standbys, and disaster recovery plan unknown |
