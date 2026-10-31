# Cynbit Backend Technical Audit & Reference Architecture

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python)](https://python.org)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg?style=flat&logo=sqlalchemy)](https://sqlalchemy.org)
[![Tests](https://img.shields.io/badge/Tests-52%20Passed-brightgreen.svg?style=flat&logo=pytest)](tests/)
[![Security](https://img.shields.io/badge/Security-Double%20Opt--In%20%7C%20SPF%20%7C%20DKIM%20%7C%20DMARC%20%7C%20Disaster%20Recovery-blue.svg)](newsletter-architecture.md)

This repository contains the **Backend Technical Audit** of Cynbit ([https://www.cynbit.in/](https://www.cynbit.in/)) conducted as part of the Backend Developer Intern technical evaluation, alongside independent reference implementations, security tools, and disaster recovery specifications:
1. **Newsletter Engine:** Double Opt-In subscription engine with cryptographic SHA-256 token hashing (`app/`).
2. **Contact Validation Service:** Whitespace-resilient validation and side-effect isolation (`contact-validation.py`).
3. **Email Security Monitor:** DNS-based verification tool for SPF, DKIM, and DMARC (`email-security-monitor.py`).
4. **Error Handling & Observability API:** Centralized exception handling, correlation ID tracking, and stack-trace suppression (`code-examples/error_responses.py`).
5. **Performance, Caching & Pagination Architecture:**
   - Offset and keyset pagination patterns ([code-examples/pagination.py](code-examples/pagination.py)).
   - Distributed Redis rate limiting with `Retry-After` headers ([code-examples/rate_limiting.py](code-examples/rate_limiting.py)).
   - ETag generation, conditional GET revalidation (`HTTP 304`), and Cache-Control strategies ([code-examples/caching.py](code-examples/caching.py)).
6. **Disaster Recovery & Availability Architecture:**
   - Hosting dependency and failure mode analysis ([architecture/disaster-recovery-architecture.md](architecture/disaster-recovery-architecture.md)).
   - Ten-step operational disaster recovery runbook ([architecture/disaster-recovery-runbook.md](architecture/disaster-recovery-runbook.md)).
7. **Client Storage & Cookie Security:** Safe credential management and anti-CSRF protection (`examples/secure-cookie-auth.py` and `examples/client-storage-demo.js`).

---

## 1. Executive Summary & Audit Context

During black-box testing of Cynbit's public backend workflows, hosting infrastructure, and client-side storage, six distinct interaction streams were audited:

### 1. Hosting Dependency, Availability & Disaster Recovery (`https://www.cynbit.in/`)
- **Hosting Tier:** Web traffic terminates on the **Vercel** platform (`server: Vercel` response header).
- **Concentration Risk:** Exclusive reliance on a single managed platform creates a single point of failure (SPOF) during platform-wide control plane or global routing disruptions.
- **Unverified Resiliency:** Internal database backup schedules, offsite replication, and recovery objectives (RTO/RPO) remain unverified.
- **Recommended Posture:** Multi-region synthetic monitoring, automated offsite database backups, documented RTO/RPO objectives, and a containerized fallback deployment runbook.

### 2. Performance, Caching & Infrastructure (`https://www.cynbit.in/`)
- **Hosting & Edge Caching:** Homepage requests return `x-vercel-cache: HIT`, `Age`, and modern Brotli compression (`Content-Encoding: br`).
- **ETag & Conditional Revalidation:** Navigation requests emit `Cache-Control: public, max-age=0, must-revalidate` and valid `ETag` headers, yielding standard `HTTP 304 Not Modified` on revalidation.
- **Observability Nuance:** Vercel edge hits are positive performance indicators, not backend flaws. Static edge caching does not establish dynamic API caching behavior.

### 3. Public Newsletter Subscription Workflow (`cynbit.in`)
- **Immediate Single Opt-In Welcome Email:** Submitting an email immediately dispatches a welcome email with the subject `"Welcome to Cynbit"` without requiring email ownership verification.
- **Missing Unsubscribe Mechanism:** The received welcome email does not contain a confirmation link, preference center link, unsubscribe link, or RFC 8058 `List-Unsubscribe` headers.
- **Duplicate Feedback & User Enumeration:** Submitting an already-registered address returns `{"success": true, "message": "You're already in our intelligence network!"}`. While this proves duplicate handling exists, it enables external email enumeration.

### 4. Contact Inquiries Submission Form (`POST /contact`)
- **Whitespace-Only Input Acceptance:** Submitting required text fields (`name`, `message`) containing only whitespace characters along with a valid email bypassed validation and triggered an automated acknowledgement email (`"Thank you for contacting Cynbit"`).
- **Next.js Server Action Response:** The endpoint returns `HTTP 200` with `Content-Type: text/x-component`, characteristic of React Server Components (RSC) flight data. Receiving HTTP 200 alone does not prove persistent database storage.

### 5. Outbound Contact Acknowledgement Email (`opportunities@cynbit.in`)
- **Authentication Triad Passed:** Inspection of received RFC 5322 MIME headers in Gmail verified that the email successfully passed all three authentication protocols:
  - **SPF:** `PASS`
  - **DKIM:** `PASS`
  - **DMARC:** `PASS`
- **Rapid Delivery:** Delivered to Gmail within approximately five seconds of contact form submission.

### 6. Client-Side Browser Storage (`localStorage` on `cynbit.in`)
- **Strong Credential Hygiene:** Inspection of `localStorage` via Chrome DevTools revealed only non-sensitive marketing attribution data (`gcl_ls`) and UI state (`cynbit_newsletter_seen`).
- **No Credentials Exposed:** No JWTs, session tokens, refresh tokens, or PII were found in JavaScript-accessible storage, successfully mitigating XSS credential theft risks.

> [!NOTE]  
> **Testing Disclaimer:** These observations are based strictly on passive inspection and non-intrusive testing of public endpoints with tester-controlled email addresses. No unauthorized access, internal probing, or disruption of Cynbit's production infrastructure was performed.

---

## 2. Summary of Audit Findings & Observations

| Finding ID | Title | Status / Severity | Category | Remediation / Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **`CYN-AUD-001`** | Absence of Double Opt-In Email Verification | **Medium** | Anti-Abuse & Data Integrity | Enforce two-way token verification before subscription activation |
| **`CYN-AUD-002`** | Missing Unsubscribe Mechanism & Headers | **Medium** | Regulatory Compliance | Inject unsubscribe link & RFC 8058 headers |
| **`CYN-AUD-003`** | Email Enumeration via Duplicate Response | **Low** | Privacy & Information Disclosure | Normalize API responses to be strictly idempotent |
| **`CYN-AUD-004`** | Mail-Bombing Vector via Public Form | **Medium** | Abuse Prevention | Sliding-window IP rate limiting & bot defense |
| **`OBS-04`** | Outbound Email Authentication | **Positive Observation** | Email Security | Maintain current SPF/DKIM/DMARC; monitor `rua` reports |
| **`OBS-05`** | Browser Local Storage Inspection | **Positive Observation** | Client-Side Data Security | Maintain HttpOnly cookies; keep `localStorage` strictly for UI state |
| **`F-04`** | Insufficient Whitespace-Only Input Validation | **Medium** | Input Validation & Data Integrity | Enforce server-side `.strip()` trimming; isolate email side effects |
| **`OBS-06`** | Error-Handling Observability & Resilience | **Informational** | Error Handling & Observability | Implement centralized exception handlers, correlation IDs, and zero stack trace leaks |
| **`PERF-01`** | Edge CDN Caching & Brotli Compression | **Positive Indicator** | Performance & Infrastructure | Vercel Edge Cache HIT observed; Brotli compression active |
| **`PERF-02`** | Conditional Revalidation (ETag / 304) | **Positive Indicator** | Performance & Caching | HTTP 304 Not Modified verified on repeat navigation |
| **`OBS-07`** | Hosting Dependency & Disaster Recovery | **Informational** | Availability & Resilience | Offsite database snapshots, defined RTO/RPO, and standby failover runbook |

Full details are documented in:
- [newsletter-audit.md](newsletter-audit.md)
- [email-authentication-audit.md](email-authentication-audit.md)
- [local-storage-audit.md](local-storage-audit.md)
- [whitespace-validation-audit.md](whitespace-validation-audit.md)
- [report/error-handling-findings.md](report/error-handling-findings.md)
- [report/performance-findings.md](report/performance-findings.md)
- [architecture/disaster-recovery-architecture.md](architecture/disaster-recovery-architecture.md)
- [architecture/disaster-recovery-runbook.md](architecture/disaster-recovery-runbook.md)
- [browser-security-recommendations.md](browser-security-recommendations.md)

---

## 3. Disaster Recovery Architecture & Operational Runbook

Comprehensive failure mode analysis and operational recovery steps are detailed in:
- **Architecture Specification:** [architecture/disaster-recovery-architecture.md](architecture/disaster-recovery-architecture.md)
- **10-Step Operational Runbook:** [architecture/disaster-recovery-runbook.md](architecture/disaster-recovery-runbook.md)

### Key Disaster Recovery Highlights:
- **Failure Analysis:** Evaluates 7 distinct outage scenarios: Vercel platform-wide, regional edge, serverless runtime, CDN asset, DNS provider, database provider, and transactional email outages.
- **RTO & RPO Definitions:** Explains Recovery Time Objective (target downtime limit) and Recovery Point Objective (target data loss window) with concrete examples.
- **Durable Form Processing:** Proposes asynchronous queue buffering (SQS / QStash) to prevent form submissions from silently disappearing during database blips.
- **Multi-Cloud Trade-Offs:** Explains the operational complexity and high cost of active-active multi-cloud setups, recommending cost-effective containerized warm/cold standby deployments instead.

---

## 4. Repository Structure

```
cynbit-backend-audit/
├── README.md                          # Comprehensive audit & implementation guide
├── newsletter-audit.md                # Formal newsletter audit report (CYN-AUD-001 - 004)
├── email-authentication-audit.md      # Outbound email security audit (Finding OBS-04)
├── local-storage-audit.md             # Client-side storage audit (Finding OBS-05)
├── whitespace-validation-audit.md     # Input validation audit report (Finding F-04)
├── browser-security-recommendations.md# Storage best practices & cookie architecture guide
├── newsletter-architecture.md         # Full architecture specification & API examples
├── contact-validation.py              # CLI & runner for validated contact submission engine
├── contact_validation.py              # Contact form FastAPI application & validation models
├── email-security-monitor.py          # CLI tool for DNS email authentication monitoring
├── email_security_monitor.py          # Core Pydantic & dnspython monitor library
├── requirements.txt                   # Production & test dependencies
├── pytest.ini                         # Pytest test suite configuration
│
├── app/                               # FastAPI Reference Implementation (Newsletter)
│   ├── config.py                      # Centralized configuration & settings
│   ├── database.py                    # SQLAlchemy session & SQLite/Postgres engine
│   ├── models.py                      # PostgreSQL-compatible ORM models (Hashed tokens)
│   ├── schemas.py                     # Pydantic v2 schemas with input normalization
│   ├── security.py                    # Cryptographic token generator & SHA-256 hasher
│   ├── middleware/
│   │   └── rate_limiter.py            # Sliding-window IP rate limiter
│   ├── services/
│   │   ├── email_service.py           # Transactional mailer with RFC 8058 headers
│   │   └── subscription_service.py    # Atomic subscription lifecycle service
│   └── api/
│       ├── deps.py                    # Rate-limiting & DB dependencies
│       └── v1/
│           └── newsletter.py          # /subscribe, /verify, /unsubscribe endpoints
│
├── code-examples/                     # Modular Performance & Security Architectures
│   ├── pagination.py                  # Offset & Keyset pagination with metadata & validation
│   ├── rate_limiting.py               # Distributed Redis rate limiting with Retry-After
│   ├── caching.py                     # ETag generation, 304 Not Modified & Cache-Control
│   ├── exceptions.py                  # Standardized domain exception hierarchy
│   ├── error_responses.py             # Centralized error handling & correlation ID API
│   └── validation.py                  # RFC-compliant email normalization & sanitization
│
├── examples/                          # Independent Educational Security Demonstrations
│   ├── secure-cookie-auth.py          # FastAPI HttpOnly cookies & CSRF protection API
│   └── client-storage-demo.js         # JavaScript storage security & XSS simulation
│
├── tests/                             # Comprehensive Automated Test Suite (52 Tests)
│   ├── conftest.py                    # Test database fixtures & state isolation
│   ├── test_newsletter.py             # 14 tests for newsletter security & workflows
│   ├── test_email_security_monitor.py # 12 unit tests for SPF/DKIM/DMARC DNS auditor
│   ├── test_contact_validation.py     # 12 unit tests for contact form input validation
│   ├── test_error_handling.py         # 6 unit tests for error handling & correlation IDs
│   └── test_performance_features.py  # 8 unit tests for pagination, Redis rate limiting & ETags
│
├── report/                            # Modular Audit Documentation
│   ├── backend-audit.md               # Executive summary report
│   ├── security-findings.md           # Security & compliance findings
│   ├── performance-findings.md        # Performance, caching, pagination & rate limiting audit
│   ├── recommendations.md             # Prioritized engineering roadmap
│   └── error-handling-findings.md     # Error handling, Next.js Server Actions & observability
│
├── architecture/                      # Architecture Diagrams, DR & Runbooks
│   ├── current-observations.md        # Black-box interaction observations
│   ├── disaster-recovery-architecture.md # DR architecture, failure analysis & RTO/RPO
│   ├── disaster-recovery-runbook.md   # 10-step incident response & failover SOP
│   └── proposed-architecture.png      # High-resolution visual architecture diagram
│
└── evidence/                          # Inspection Artifacts
    ├── screenshots/                   # Evidence screenshot directory
    └── network-analysis.md            # HTTP payload and network trace analysis
```

---

## 5. Local Execution & Testing Guide

### Prerequisites
- Python 3.10+ (tested on Python 3.14)
- Git

### Installation
```bash
git clone https://github.com/manasvaidya18/cynbit-backend-audit.git
cd cynbit-backend-audit
pip install -r requirements.txt
```

### Running Individual Services
```bash
# 1. Main Newsletter Engine (Double Opt-In, SHA-256 tokens)
uvicorn app.main:app --reload --port 8000

# 2. Contact Form Validation Service (Whitespace-resilient)
python contact-validation.py

# 3. Distributed Redis Rate Limiter Service
uvicorn code-examples.rate_limiting:app --port 8005

# 4. HTTP Caching & ETag Revalidation Service
uvicorn code-examples.caching:app --port 8006

# 5. Centralized Error Handling & Correlation ID Service
uvicorn code-examples.error_responses:app --port 8003

# 6. Email Security DNS Monitor CLI
python email-security-monitor.py --compact cynbit.in
```

### Running the Test Suite (52/52 Tests Passed)
```bash
pytest -v
```

All 52 automated tests execute in **< 0.6 seconds**:
- **Newsletter Subscription Suite (14 Tests):** Double Opt-In lifecycle, token hashing, single-use clearing, duplicate idempotency, rate limiting.
- **Email Security Monitor Suite (12 Tests):** SPF multiple-record error handling, DMARC policies, DKIM key extraction, mock DNS resolution failures.
- **Contact Input Validation Suite (12 Tests):** Valid contact submissions, whitespace-only name/message rejection, empty string handling, character bounds, optional field normalization, side-effect isolation.
- **Error Handling & Observability Suite (6 Tests):** Successful 200 with correlation ID, structured 422 validation, expected 404/409 domain errors, unexpected 500 with zero stack-trace leakage, and custom correlation ID header propagation.
- **Performance, Caching & Pagination Suite (8 Tests):** Pagination boundary validation (`limit`, `offset`), stable deterministic ordering, Redis rate limiting with `Retry-After`, ETag generation, conditional `HTTP 304 Not Modified`, and private/no-store caching policies.
