# Standard Operating Procedure: Disaster Recovery & Outage Response Runbook

**System:** Cynbit Web Application & Backend Services  
**Document Type:** Disaster Recovery Standard Operating Procedure (SOP)  
**Classification:** Operational Runbook  
**Auditor Reference:** Cynbit Backend Technical Audit Reference Suite  
**Date:** November 2026  

---

## 1. Incident Command & Role Placeholders

During an active severity-1 (Sev-1) or severity-2 (Sev-2) outage, operations must be coordinated by designated incident roles:

| Role Placeholder | Primary Responsibility |
| :--- | :--- |
| `[Incident Commander]` | Leads triage, declares incident severity, coordinates cross-team actions, and issues external communications. |
| `[Lead Backend Engineer]` | Investigates runtime errors, database connectivity, serverless execution logs, and API status. |
| `[DevOps / Infrastructure Lead]` | Manages DNS failover, edge routing, cloud provider status pages, secrets, and container provisioning. |
| `[QA / Verification Lead]` | Executes end-to-end smoke tests (homepage, contact form, newsletter verification) post-failover. |

---

## 2. Ten-Step Disaster Recovery Procedure

```
+-----------------------------------------------------------------------------------------+
|                                10-STEP RECOVERY TIMELINE                                |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|  [PHASE 1: TRIAGE]                                                                      |
|  Step 1: Detect & Acknowledge -> Step 2: Regional vs Global -> Step 3: Check Dep. Health|
|                                                                                         |
|  [PHASE 2: DECISION & ACTIVATION]                                                       |
|  Step 4: Assess Impact -> Step 5: Activate Standby Host -> Step 6: Verify Env & DB      |
|                                                                                         |
|  [PHASE 3: TRAFFIC CUTOVER & VALIDATION]                                                |
|  Step 7: Switch DNS Traffic -> Step 8: Execute Smoke Tests -> Step 9: Monitor Errors   |
|                                                                                         |
|  [PHASE 4: RESTORATION & POST-MORTEM]                                                   |
|  Step 10: Failback to Primary & Post-Incident Review                                    |
+-----------------------------------------------------------------------------------------+
```

### Step 1: Detect and Acknowledge the Outage
- **Action:** Automated synthetic monitoring alert triggers in Slack/PagerDuty (`HTTP 5xx rate > 5%` or `Unreachable from 3+ probe locations`).
- **Owner:** `[Incident Commander]`
- **Procedure:**
  1. Acknowledge alert in PagerDuty within 5 minutes.
  2. Open an incident bridge (Slack war room: `#incident-outage-YYYYMMDD`).
  3. Record the initial incident timestamp: $T_{\text{start}}$.

### Step 2: Determine Scope (Regional vs. Platform-Wide)
- **Action:** Assess whether the failure is localized to a single geographic edge or spans the entire platform.
- **Owner:** `[DevOps / Infrastructure Lead]`
- **Procedure:**
  1. Check Vercel Status Page ([https://www.vercel-status.com](https://www.vercel-status.com)) for active incidents.
  2. Review synthetic monitoring regional breakdown (e.g., is failure isolated to Asia-Pacific/Mumbai `bom1` or global?).
  3. If **regional**: Vercel Anycast edge routing should automatically redirect traffic within 5–10 minutes. Standby failover is usually **not** required.
  4. If **platform-wide (global)**: Proceed immediately to dependency health inspection.

### Step 3: Check Dependencies Independently
- **Action:** Verify whether the outage is confined to Vercel or if upstream data tiers are impacted.
- **Owner:** `[Lead Backend Engineer]`
- **Procedure:**
  1. **Database Tier:** Connect directly to the managed database (e.g., Supabase / Neon / AWS RDS) via command line / bastion to verify read/write health.
  2. **DNS Authority:** Query authoritative nameservers via `dig +trace cynbit.in` to ensure DNS records are resolving.
  3. **Transactional Email:** Check email provider status (AWS SES / SendGrid / Postmark).

### Step 4: Assess Impact on Website & Submissions
- **Action:** Quantify client-facing failure modes.
- **Owner:** `[Incident Commander]`
- **Procedure:**
  1. Can visitors view cached static pages?
  2. Are contact submissions (`POST /contact`) failing or timing out?
  3. Are newsletter subscriptions (`POST /subscribe`) erroring out?
  4. Decision gate: If Vercel platform-wide outage exceeds 30 minutes and estimated resolution is unknown, initiate **Step 5 (Standby Activation)**.

### Step 5: Activate Alternate Deployment (Proposed Standby)
- **Action:** Boot the emergency fallback application instance (e.g., containerized Next.js service on AWS App Runner / Fly.io).
- **Owner:** `[DevOps / Infrastructure Lead]`
- **Procedure:**
  1. Trigger standby deployment using the pre-built Docker image from the container registry:
     ```bash
     # Example emergency trigger (AWS / Alternate Host)
     aws apprunner start-deployment --service-arn <STANDBY_SERVICE_ARN>
     ```
  2. Confirm container initialization and health check (`/health` returning `200 OK`).

### Step 6: Verify Environment Variables, Secrets & Database Connectivity
- **Action:** Ensure the standby instance is configured with production secrets and can communicate securely with the primary database.
- **Owner:** `[Lead Backend Engineer]`
- **Procedure:**
  1. Verify `DATABASE_URL` matches the production database cluster.
  2. Verify API keys for transactional email dispatch.
  3. Verify security token signing secrets (`SECRET_KEY`).
  4. Run database connection test query.

### Step 7: Switch Traffic Using Documented Failover Process
- **Action:** Re-route external traffic from Vercel to the healthy standby host.
- **Owner:** `[DevOps / Infrastructure Lead]`
- **Procedure:**
  1. Navigate to DNS Management Console (Cloudflare / Route 53).
  2. Update the root apex / `www` DNS records:
     - Change CNAME from `cname.vercel-dns.com` to the standby hostname (e.g., `standby.cynbit-dr.aws.com`).
     - Set DNS TTL to **60 seconds** to allow rapid propagation and subsequent rollback.
  3. Confirm global DNS propagation via `dig cynbit.in @1.1.1.1`.

### Step 8: Execute End-to-End Smoke Tests
- **Action:** Validate core business workflows on the live standby system.
- **Owner:** `[QA / Verification Lead]`
- **Procedure:**
  1. Load homepage `https://www.cynbit.in/` (verify layout, branding, SSL certificate).
  2. Submit test contact inquiry with tester-owned email (verify `200 OK` and receipt of acknowledgement email).
  3. Submit test newsletter subscription (verify Double Opt-In token email delivery and successful verification link click).

### Step 9: Monitor Errors and Inbound Delivery
- **Action:** Closely monitor error logs and inbound submission rates on the standby host.
- **Owner:** `[Lead Backend Engineer]`
- **Procedure:**
  1. Stream server logs: check for database connection pool exhaustion or unhandled 5xx exceptions.
  2. Monitor transactional mail queue for bounce rate spikes.
  3. Update external status page (e.g., `status.cynbit.in`): notify users that services are operating on contingency infrastructure.

### Step 10: Restore Normal Traffic (Failback) & Post-Mortem
- **Action:** Return traffic to primary Vercel hosting once stability is officially verified.
- **Owner:** `[Incident Commander]`
- **Procedure:**
  1. Verify Vercel platform incident is marked "Resolved" and stable for at least 30 minutes.
  2. Revert DNS CNAME records back to Vercel edge endpoints (`cname.vercel-dns.com`).
  3. Repeat smoke tests on Vercel deployment.
  4. Decommission / spin down warm standby capacity to minimize cloud hosting costs.
  5. Schedule a Blameless Post-Mortem within 48 hours to document root cause, downtime duration ($T_{\text{RTO}}$), and remediation items.

---

## 3. Rollback Considerations

If the standby deployment experiences fatal configuration errors during Step 7:
1. **Immediate Abort:** Immediately revert DNS records back to primary or point traffic to a static maintenance page (e.g., hosted on AWS S3 / Cloudflare Pages) displaying a friendly maintenance message.
2. **Prevent Split-Brain Inconsistencies:** If the standby instance wrote records to a fallback database, coordinate an immediate database synchronization script before returning to the primary database.

---

## 4. Responsible Owner Placeholders

- **Primary Escalation Contact:** `[Head of Engineering / On-Call SRE]`
- **Secondary Escalation Contact:** `[CTO / Technical Operations Lead]`
- **Incident Bridge Channel:** `[#incident-war-room]`
