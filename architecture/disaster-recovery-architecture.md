# Technical Audit: Hosting Dependency, Availability & Disaster Recovery Architecture

**Target Entity:** Cynbit ([https://www.cynbit.in/](https://www.cynbit.in/))  
**Assessment Context:** Backend Developer Intern Assessment – Resilience & Disaster Recovery Audit  
**Auditor:** Manas Vaidya  
**Date:** November 2026  
**Audited Target:** Hosting Infrastructure, Availability Boundaries & Failure Resilience  

---

## 1. Documented Evidence & Architectural Baseline

### 1.1 Confirmed Observations
- **Hosting Provider:** Public HTTP responses from `https://www.cynbit.in/` include the header `server: Vercel`, confirming that edge routing and web serving terminate at Vercel's global infrastructure.
- **Application Framework:** Response headers such as `x-vercel-cache` and `text/x-component` confirm that the application is built using the **Next.js** framework (App Router) and deployed via Vercel's managed serverless runtime.
- **Server Actions:** Form submissions (e.g. `POST /contact`) execute via Next.js Server Actions streaming flight data back over the primary origin path.

### 1.2 Reasonable Architectural Inferences
- **Decoupled Backend Services:** In standard Next.js Vercel deployments, the frontend web tier does not host persistent database engines. Data storage (relational database, document store) is almost certainly delegated to an external managed database provider (e.g., Supabase, Neon, AWS RDS, PlanetScale, or MongoDB Atlas).
- **External Email Delivery Provider:** Transactional emails originating from `opportunities@cynbit.in` with passing SPF, DKIM, and DMARC indicate integration with a dedicated transactional email service provider (e.g., Google Workspace, AWS SES, SendGrid, or Resend) rather than self-hosted SMTP relays.

### 1.3 Unverified Infrastructure Details
The following operational details cannot be established via external black-box testing and remain **unknown**:
- The identity and geographic location of the persistent database provider.
- Database backup schedules, retention windows, point-in-time recovery (PITR) capabilities, and offsite replication.
- Deployment regions configured for Vercel Functions (e.g. `iad1`, `bom1`, `sfo1`).
- The existence of staging, preview, or secondary disaster-recovery environments.
- Form submission buffering, asynchronous task queues, or dead-letter queue (DLQ) implementations.

---

## 2. Infrastructure Failure Scenarios & Impact Analysis

Modern web reliability engineering requires evaluating how single-point-of-failure (SPOF) disruptions cascade across dependent tiers:

| Failure Scenario | Potential User Impact | Functionality Rendered Unavailable | Dependencies That May Remain Operational | Possible Recovery Approach |
| :--- | :--- | :--- | :--- | :--- |
| **1. Vercel Platform-Wide Outage** (Global edge or control-plane failure) | Total website unavailability; browser displays DNS resolution timeout, generic HTTP 502/503, or Vercel platform error. | Entire public website, static assets, marketing pages, contact form, and newsletter subscription form. | External database, transactional email provider, DNS nameservers (if external), third-party monitoring. | Activate secondary static fallback (e.g., AWS S3 + CloudFront or Cloudflare Pages) via DNS record update (`CNAME` / `A` failover); deploy containerized Next.js build to an alternate cloud host. |
| **2. Regional Vercel Outage** (Single edge region or AWS AZ disruption) | Users in the affected geographic region experience elevated latency or connection drops. | Serverless function execution routed through the impaired region; edge asset delivery. | Unaffected global regions; centralized managed database; transactional email delivery. | Automatic edge failover: Vercel Anycast edge routing typically re-routes traffic to the nearest healthy geographical point-of-presence (PoP). |
| **3. Vercel Functions Outage** (Serverless runtime execution failure) | Website pages render if statically cached; submitting contact or newsletter forms fails with application errors. | Dynamic Server Actions (`POST /contact`), newsletter subscription (`POST /subscribe`), dynamic server-side rendering. | Edge-cached static content, CDN assets (CSS, JS, images), third-party external services. | Serve graceful client-side maintenance feedback; disable form submit buttons with informative user alerts; investigate Vercel runtime status and rollback recent deployments. |
| **4. CDN / Static Asset Outage** | Broken styling, missing JavaScript chunks, unformatted HTML layout, hydration failures. | Interactive client-side components, analytics tracking scripts, dynamic modal dialogs. | Origin serverless functions, database tier, external email delivery APIs. | Invalidate CDN cache; purge stale asset manifests; redeploy clean production build with updated asset hashes. |
| **5. DNS Provider Outage** (Authoritative nameserver resolution failure) | Global domain resolution failure (`NXDOMAIN` or `ERR_NAME_NOT_RESOLVED`); zero traffic reaches Vercel. | Entire domain ecosystem, web portal, API endpoints, incoming/outgoing email delivery (if MX impacted). | Underlying Vercel deployments, databases, and third-party SaaS services (accessible via direct IPs/subdomains). | Maintain dual authoritative nameservers (e.g. Cloudflare + Route 53); configure automated secondary DNS zone transfer (RFC 1995/5936). |
| **6. Database Provider Outage** | Users can load cached static pages; submitting forms or fetching dynamic data triggers HTTP 500 errors. | Contact inquiries, subscriber registration, user authentication, profile data retrieval. | Vercel edge CDN, static assets, email provider infrastructure (ready to send, but starved of triggers). | Failover to hot read-replica; queue incoming submissions in durable transient buffer (e.g., AWS SQS / QStash) rather than failing immediately. |
| **7. Transactional Email Provider Outage** | Website functions normally; users submit forms successfully but never receive acknowledgement or confirmation emails. | "Thank you for contacting Cynbit" emails, Double Opt-In newsletter confirmation tokens. | Web serving, database persistence, form input validation, rate limiting. | Asynchronous job queuing with exponential retry backoff; secondary backup SMTP relay failover (e.g. Postmark fallback for AWS SES). |

---

## 3. Audit Finding: Hosting Dependency & Unverified Disaster Recovery

### Finding Overview
- **Finding ID:** `OBS-07`
- **Title:** Hosting Provider Dependency and Unverified Disaster Recovery Strategy
- **Category:** Availability, Infrastructure & Resilience
- **Classification:** Availability and resilience risk
- **Status:** **Informational / Resilience Assessment**
- **Provisional Severity:** **Medium**
- **Confidence Level:** **Limited** (Evaluated from external edge responses; internal recovery arrangements and operational playbooks are unknown)

### Technical Analysis
1. **Hosting Provider Concentration Risk:**
   Relying exclusively on a single managed platform (Vercel) for edge routing, asset delivery, and compute logic introduces a single point of failure (SPOF). While managed edge platforms maintain high availability service level agreements (SLAs), multi-tenant platform outages (such as global edge routing degradations or identity provider outages) will take down all web operations simultaneously.
2. **Limits of Regional Redundancy:**
   Next.js edge routes can be distributed across multiple geographical points of presence. However, regional redundancy **does not protect** against platform-wide control plane incidents, domain-level configuration lockouts, account billing suspensions, or global CDN routing disruptions.
3. **The Imperative of Independent Database Backups:**
   If a managed database service experiences data corruption, ransomware, accidental schema drops, or catastrophic physical datacenter failure, backups residing within that same provider's infrastructure may be inaccessible. Maintaining automated, encrypted, offsite database snapshots stored in an isolated cloud provider (e.g. AWS S3 in a separate geography) is essential.
4. **Preventing Silent Data Loss:**
   When an upstream service (such as the database or email relay) experiences a transient network blip during a contact form submission, an unbuffered application will return an error and discard the user's input. Business inquiries and threat reports represent high-value leads; they should be queued durably (or preserved in client-side drafts) rather than silently lost.

> [!IMPORTANT]  
> **Testing Boundary Disclaimer:**  
> This finding reflects the architectural risks inherent in single-provider web deployments. It **does not claim** that Cynbit lacks backups, redundancy, or disaster recovery procedures. Those operational arrangements are internal and have not been evaluated.

---

## 4. Proportionate Resilience & Architecture Recommendations

To balance operational resilience with engineering overhead, the following ten improvements are recommended:

### 4.1 Uptime Monitoring and Health Checks
- Deploy multi-region synthetic monitoring probes (e.g., Datadog Synthetics, Better Stack, or UptimeRobot) operating across multiple global continents.
- Configure probes for:
  - Homepage availability (`GET /`) verifying HTTP 200 and expected DOM elements.
  - Deep health check endpoint (`GET /health`) actively verifying database connectivity and Redis cache responsiveness.
- Configure alert escalation policies to PagerDuty or Slack for latency spikes > 2000ms or consecutive 5xx errors.

### 4.2 Independent Database Backups
- Establish automated daily full database snapshots alongside continuous Write-Ahead Log (WAL) archiving.
- Export snapshots and WAL streams to an **independent cloud storage provider** (e.g., AWS S3 or Cloudflare R2) in an isolated account with separate IAM access keys.
- Enforce immutability / Object Lock policies on backup buckets to defend against accidental deletion or ransomware.

### 4.3 Periodic Backup Restoration and Disaster Recovery Testing
- A backup that has never been restored is not a reliable backup.
- Conduct scheduled periodic (e.g., quarterly) restoration drills into an isolated staging environment.
- Measure actual restoration elapsed time against the target RTO and verify database integrity and data completeness.

### 4.4 Defined Recovery Time Objective (RTO)
- **Concept:** RTO represents the maximum acceptable duration of system downtime before service must be fully restored.
- **Example:** If the business establishes an RTO of **4 hours**, all failover procedures, server provisioning scripts, and DNS cutover steps must execute and verify within 240 minutes of incident declaration.
- *Status:* RTO is a business-level decision that must be agreed upon between engineering leadership and executive stakeholders.

### 4.5 Defined Recovery Point Objective (RPO)
- **Concept:** RPO represents the maximum acceptable age of data loss measured backward from the point of failure.
- **Example:** If the business establishes an RPO of **1 hour**, backups or continuous WAL synchronization must occur at intervals no greater than 60 minutes, ensuring at most 1 hour of newly submitted contact or newsletter signups are at risk during catastrophic storage failure.
- *Status:* RPO is a business-level decision that must be agreed upon based on data criticality.

### 4.6 Graceful Failure Handling and Maintenance Responses
- Prevent raw, unstyled 502/503/504 gateway error pages from reaching visitors during upstream failures.
- Implement client-side error boundaries with informative, branded fallback alerts (e.g., "Our servers are experiencing a brief interruption; please retry in a few moments").
- Configure an external static maintenance page (hosted on Cloudflare Pages or AWS S3) that can be activated instantly if the primary web origin is unreachable.

### 4.7 Durable Form Submission Processing Where Justified
- Submissions on `/contact` represent high-priority commercial and partnership inquiries that should not be dropped due to transient backend blips.
- Decouple form intake from synchronous database transactions using an asynchronous queue (e.g., Upstash QStash, AWS SQS, or Redis BullMQ).
- The web function ingests the payload, enqueues it, and immediately returns a client tracking receipt. Dedicated worker processes persist the record to the database with exponential backoff retries.

### 4.8 Documented Alternate-Provider Deployment Procedure
- Maintain a production-ready `Dockerfile` and container build pipeline in the repository.
- Document step-by-step instructions for deploying this container to a secondary container runtime (e.g., AWS App Runner, Fly.io, or Render) if Vercel suffers an extended platform-wide outage.
- Store pre-built container images in an independent registry (e.g., Amazon ECR or GitHub Packages).

### 4.9 DNS or Traffic Failover Where Appropriate
- Configure low TTLs (e.g., 60–300 seconds) on authoritative apex (`@`) and `www` DNS records.
- Implement health-check-driven automated or 1-click manual DNS failover via Anycast DNS (e.g., Cloudflare or AWS Route 53) to quickly route visitors to the alternate deployment or maintenance landing page.

### 4.10 Monitoring for Email Delivery Failures
- Implement webhook alerting on transactional email provider events (e.g., AWS SES Configuration Sets, SendGrid Event Webhooks, or Postmark Webhooks) to track bounces, spam complaints, and dispatch drop-offs.
- Enforce dead-letter queuing (DLQ) for unfulfilled transactional emails so failed notifications can be replayed once the mail provider recovers.
- Maintain a secondary fallback SMTP configuration for critical transactional messages.

### 4.11 Cost and Operational Complexity of Multi-Cloud Deployment
- **Complexity Analysis:** Operating an active-active multi-cloud architecture (e.g., running identical live production environments on Vercel and AWS concurrently) introduces severe challenges:
  - Complex two-way cross-cloud database replication with latency and conflict-resolution overhead.
  - Substantial egress data transfer costs between cloud providers.
  - Increased attack surface across multiple cloud IAM and network configurations.
  - Continuous synchronization of environment variables, edge configs, and CI/CD pipelines.
- **Proportionate Recommendation:** An active-active multi-cloud deployment is **not recommended** as mandatory for early or growth stage web applications without specific regulatory or high-nines enterprise SLA requirements. A **cold or warm standby** architecture (documented container build + automated DNS failover) provides optimal resilience at a fraction of the cost and complexity.

---

## 5. Proposed Disaster Recovery Architecture

```mermaid
flowchart TD
    subgraph Clients["External Users & Clients"]
        User["End User Browser"]
    end

    subgraph Edge["DNS & Traffic Routing Tier"]
        DNS["Authoritative Anycast DNS<br/>(Cloudflare / Route 53)"]
        HealthCheck["Synthetic Health Prober<br/>(Better Stack / Datadog)"]
    end

    subgraph PrimaryInfra["PRIMARY HOSTING (Vercel Platform)"]
        VercelEdge["Vercel Edge CDN<br/>(Anycast Cache & Brotli)"]
        VercelFunc["Next.js Serverless Functions<br/>(/contact & /subscribe Server Actions)"]
    end

    subgraph ProposedStandby["PROPOSED SECONDARY (Warm/Cold Standby - AWS)"]
        ALB["AWS Application Load Balancer"]
        ECS["Containerized Next.js Service<br/>(AWS ECS / App Runner)"]
    end

    subgraph DataTier["INDEPENDENT DATA & SERVICES TIER"]
        DB[("Managed PostgreSQL Database<br/>(e.g., AWS RDS / Neon)")]
        EmailSvc["Transactional Email Provider<br/>(AWS SES / SendGrid)"]
        OffsiteBackup[("Offsite Encrypted S3 / R2 Bucket<br/>(Daily Snapshots & WAL Archives)")]
    end

    subgraph Alerts["ALERTING & OBSERVABILITY"]
        OpsAlerts["PagerDuty / Slack On-Call<br/>(SRE & Engineering)"]
    end

    %% User traffic flows
    User -->|1. Resolve cynbit.in| DNS
    DNS -->|2a. Primary Route| VercelEdge
    VercelEdge --> VercelFunc
    VercelFunc -->|Read/Write Data| DB
    VercelFunc -->|Dispatch Mails| EmailSvc

    %% Proposed Failover Route
    DNS -.->|2b. Emergency Failover Route<br/>(Proposed Option)| ALB
    ALB -.-> ECS
    ECS -.->|Fallback Connection| DB

    %% Backups & Health Probing
    DB -->|Continuous WAL & Snapshots| OffsiteBackup
    HealthCheck -->|Probes /health| VercelEdge
    HealthCheck -->|Probes Health| ALB
    HealthCheck -->|Trigger Incident| OpsAlerts
```

> [!NOTE]  
> The secondary AWS deployment in the diagram is a **proposed emergency standby option** designed for high-availability contingency planning. It is not an observed part of Cynbit's current production setup.
