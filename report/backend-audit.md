# Cynbit Backend Technical Audit Report

**Target:** Cynbit ([https://www.cynbit.in/](https://www.cynbit.in/))  
**Assessment:** Backend Developer Intern Technical Audit  
**Auditor:** Manas Vaidya  
**Date:** November 2026  

---

## Executive Summary

This report compiles the comprehensive findings from an external black-box audit of Cynbit's public backend workflows, hosting infrastructure, client-side data handling, and disaster recovery posture. The assessment evaluates backend architecture, security controls, email deliverability hygiene, data protection compliance, email authentication, client-side storage security, input validation integrity, error-handling observability, and availability resilience.

### Scope and Boundaries
- Target workflows:
  1. Public newsletter subscription input on `cynbit.in`.
  2. Public contact inquiries submission form on `cynbit.in` (`POST /contact`).
  3. Automated contact form acknowledgement stream from `opportunities@cynbit.in`.
  4. Client-side browser storage (`localStorage`) on origin `https://www.cynbit.in`.
  5. Infrastructure headers, Vercel edge caching, and conditional revalidation.
  6. Hosting provider dependency, failure mode analysis, and disaster recovery architecture.
- Methodology: Passive observation and active submission of tester-controlled test accounts.
- Constraints: No private endpoints were probed; no denial-of-service tests or brute-force requests were sent to Cynbit's live systems.

### Key Audit Findings & Observations Overview
1. **[CYN-AUD-001] Single Opt-In Email Processing:** Immediate dispatch of welcome emails without two-way verification creates vulnerability to third-party subscription bombing.
2. **[CYN-AUD-002] Omission of Unsubscribe Mechanism in Welcome Mail:** Welcome emails omit one-click unsubscribe links and RFC 8058 headers, exposing the domain to spam complaints and regulatory penalties (DPDP Act 2023 §6(4), GDPR Art. 7(3), CAN-SPAM).
3. **[CYN-AUD-003] User Enumeration via Differentiated Duplicate Feedback:** Clear distinction between existing subscribers and new submissions reveals subscriber presence to unauthenticated users.
4. **[CYN-AUD-004] Transactional Email Relay Abuse Exposure:** Public form submissions trigger immediate outbound mail dispatch without visible bot challenge or IP rate limits.
5. **[OBS-04] Outbound Email Authentication (Positive Security Observation):** Outbound transactional messages from `opportunities@cynbit.in` successfully pass all three email authentication checks (**SPF: PASS**, **DKIM: PASS**, **DMARC: PASS**) with prompt delivery (~5 seconds).
6. **[OBS-05] Browser Local Storage Inspection (Positive Security Observation):** Inspection of `localStorage` on `https://www.cynbit.in` confirmed that only non-sensitive UI state (`cynbit_newsletter_seen`) and public analytics attributes (`gcl_ls`) are stored. No authentication tokens, session IDs, or PII were observed.
7. **[F-04] Insufficient Whitespace-Only Input Validation:** The contact form accepts whitespace-only required fields (`name`, `message`) when accompanied by a valid email, triggering automated acknowledgment emails and risking CRM pollution and email relay abuse.
8. **[OBS-06] Error-Handling Observability & Server Failure Resilience (Architecture Observation):** The contact form endpoint responds with `text/x-component` consistent with Next.js Server Actions. Internal failure handling remains unobserved; recommended implementation of centralized exception handling, correlation IDs, and zero stack trace leakage.
9. **[PERF-01] Edge CDN Caching & Brotli Compression (Positive Indicator):** Responses utilize modern Brotli compression (`Content-Encoding: br`) and are served directly from Vercel's global edge cache (`x-vercel-cache: HIT`).
10. **[PERF-02] Conditional Revalidation (ETag / HTTP 304) (Positive Indicator):** Revalidation requests return standard `HTTP 304 Not Modified`, demonstrating efficient bandwidth utilization and client-side cache reuse.
11. **[OBS-07] Hosting Provider Dependency and Unverified Disaster Recovery (Resilience Assessment):** Primary serving terminates on Vercel. While regional Anycast routing is active, platform-wide outages, independent database backup procedures, and recovery objectives (RTO/RPO) remain unverified.

---

## Detailed Reports & Tools
- Security Analysis: [report/security-findings.md](security-findings.md)
- Performance & Deliverability: [report/performance-findings.md](performance-findings.md)
- Architectural Remediation Plan: [report/recommendations.md](recommendations.md)
- Error Handling & Observability Audit: [report/error-handling-findings.md](error-handling-findings.md)
- Disaster Recovery Architecture: [architecture/disaster-recovery-architecture.md](../architecture/disaster-recovery-architecture.md)
- Disaster Recovery Runbook: [architecture/disaster-recovery-runbook.md](../architecture/disaster-recovery-runbook.md)
- Current Architecture Observations: [architecture/current-observations.md](../architecture/current-observations.md)
- Newsletter Audit Document: [newsletter-audit.md](../newsletter-audit.md)
- Outbound Email Authentication Audit: [email-authentication-audit.md](../email-authentication-audit.md)
- Browser Storage Audit: [local-storage-audit.md](../local-storage-audit.md)
- Whitespace Validation Audit: [whitespace-validation-audit.md](../whitespace-validation-audit.md)
- Browser Security & Cookie Architecture Guide: [browser-security-recommendations.md](../browser-security-recommendations.md)
- Reference Implementation Architecture: [newsletter-architecture.md](../newsletter-architecture.md)
- DNS Security Monitor Tool: [email-security-monitor.py](../email-security-monitor.py)
- Contact Validation Service: [contact-validation.py](../contact-validation.py)
- Error Handling Reference API: [code-examples/error_responses.py](../code-examples/error_responses.py)
- Pagination Architecture: [code-examples/pagination.py](../code-examples/pagination.py)
- Distributed Redis Rate Limiting: [code-examples/rate_limiting.py](../code-examples/rate_limiting.py)
- Caching & ETag Revalidation: [code-examples/caching.py](../code-examples/caching.py)
- Secure Cookie Auth Example: [examples/secure-cookie-auth.py](../examples/secure-cookie-auth.py)
- Client Storage Demo: [examples/client-storage-demo.js](../examples/client-storage-demo.js)
