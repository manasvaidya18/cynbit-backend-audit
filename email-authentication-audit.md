# Technical Audit Finding: Outbound Email Authentication

**Target Entity:** Cynbit ([https://www.cynbit.in/](https://www.cynbit.in/))  
**Assessment Context:** Backend Developer Intern Assessment – Security & Infrastructure Audit  
**Auditor:** Manas Vaidya  
**Date:** November 2026  
**Audited Stream:** Outbound automated contact acknowledgement from `opportunities@cynbit.in`

---

## 1. Finding Overview: OBS-04

| Attribute | Details |
| :--- | :--- |
| **Finding ID** | `OBS-04` |
| **Finding Title** | Outbound Email Authentication (SPF, DKIM, DMARC) |
| **Category** | Email Security & Infrastructure Resilience |
| **Status** | **Positive Security Observation** |
| **Confidence Level** | **High** (Directly verified via Gmail `Authentication-Results` headers) |
| **Sending Identity** | `opportunities@cynbit.in` |
| **Observed Latency** | Delivered successfully to Google Workspace/Gmail within ~5 seconds of form submission |

---

## 2. Observed Evidence & Results

Upon submitting the contact form on `https://www.cynbit.in/`, an automated acknowledgement message was received from `opportunities@cynbit.in`. Inspection of the raw RFC 5322 MIME headers in Gmail revealed that the message passed all three critical email authentication protocols:

```email
Delivered-To: recipient@gmail.com
Received: by 2002:a05:... with SMTP id ...;
Received-SPF: pass (google.com: domain of opportunities@cynbit.in designates ... as permitted sender) client-ip=...;
Authentication-Results: mx.google.com;
       dkim=pass header.i=@cynbit.in header.s=... header.b=...;
       spf=pass (google.com: domain of opportunities@cynbit.in designates ... as permitted sender) smtp.mailfrom=opportunities@cynbit.in;
       dmarc=pass (p=quarantine sp=quarantine dis=none) header.from=cynbit.in
From: Cynbit Opportunities <opportunities@cynbit.in>
Subject: Thank you for contacting Cynbit
```

### Summary of Results:
- **SPF Check:** `PASS` — The sending Mail Transfer Agent (MTA) IP address is authorized within Cynbit's published SPF TXT record.
- **DKIM Check:** `PASS` — The cryptographic signature embedded in the `DKIM-Signature` header was successfully decrypted and verified against Cynbit's public key published in DNS (`<selector>._domainkey.cynbit.in`).
- **DMARC Check:** `PASS` — Both identifier alignment and domain matching criteria were satisfied against the `cynbit.in` organizational domain.

---

## 3. Technical Explanation of SPF, DKIM, and DMARC

Email authentication relies on three complementary, standards-based protocols designed to protect domains against impersonation, spoofing, and tampering:

```
+-----------------------------------------------------------------------------------------+
|                               EMAIL AUTHENTICATION TRIAD                                |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|  1. SPF (RFC 7208)             2. DKIM (RFC 6376)              3. DMARC (RFC 7489)      |
|  Sender Policy Framework       DomainKeys Identified Mail      Domain-based Message     |
|                                                                Auth, Reporting & Conf.  |
|  +--------------------------+  +--------------------------+  +------------------------+ |
|  | Verifies Envelope Sender |  | Cryptographically Signs  |  | Enforces Alignment:    | |
|  | IP against DNS TXT       |  | Body & Selected Headers  |  | RFC 5322 From vs       | |
|  | "v=spf1 ... ~all"        |  | Private Key -> Public Key|  | SPF / DKIM Domains     | |
|  +--------------------------+  +--------------------------+  +------------------------+ |
|               \                              /                            /             |
|                v                            v                            v              |
|          IP Authorization             Cryptographic Integrity     Policy Enforcement    |
|             (Envelope)                     (Message Body)          (User-Facing From)   |
+-----------------------------------------------------------------------------------------+
```

### 3.1 Sender Policy Framework (SPF – RFC 7208)
- **Mechanism:** SPF publishes an authorized list of server IP addresses, CIDR blocks, or external services (`include:`) permitted to send email on behalf of the domain's envelope address (`Return-Path` / `smtp.mailfrom`).
- **Verification:** The receiving mail server extracts the client IP of the connecting MTA and evaluates it against the published `v=spf1` DNS record.
- **Limitation:** SPF protects only the envelope sender (RFC 5321). It does not validate the human-readable "From" header (RFC 5322) displayed in email clients, nor does it survive email forwarding where intermediate MTAs change the connecting IP.

### 3.2 DomainKeys Identified Mail (DKIM – RFC 6376)
- **Mechanism:** DKIM adds a cryptographic digital signature to the message header (`DKIM-Signature:`). The signing MTA computes a hash of the email body and critical headers, encrypts the hash using its private key, and transmits it with the email.
- **Verification:** The receiving MTA queries DNS for the sender's public key located at `<selector>._domainkey.<domain>` and decrypts the signature. If the decrypted hash matches the recomputed message hash, authenticity and message integrity are guaranteed.
- **Advantage:** DKIM survives email forwarding because the cryptographic signature is embedded in the message payload rather than tied to the client IP address.

### 3.3 Domain-based Message Authentication, Reporting & Conformance (DMARC – RFC 7489)
- **Mechanism:** DMARC builds upon SPF and DKIM by enforcing **Identifier Alignment**. It verifies that the domain shown to the user in the visible `From:` header matches the authenticated domain from SPF and/or DKIM.
- **Policy Enforcement:** DMARC publishes instructions telling receiving mail servers how to handle unaligned or failed messages:
  - `p=none`: Monitor only (deliver message normally while generating feedback reports).
  - `p=quarantine`: Send unauthenticated messages to the recipient's Spam/Junk folder.
  - `p=reject`: Instruct receiving MTAs to reject unauthenticated messages entirely at the SMTP boundary.
- **Reporting Loop:** Configures `rua` (aggregate feedback) and `ruf` (forensic failure) endpoints to provide domain owners with continuous visibility into outbound sending activity and spoofing attempts.

---

## 4. Security & Operational Implications

1. **Strong Anti-Spoofing & Brand Protection:**
   Having valid SPF, DKIM, and DMARC ensures that malicious actors cannot forge email communications originating from `opportunities@cynbit.in`. This mitigates spear phishing, CEO fraud, and credential harvesting campaigns targeting clients or prospective candidates.
2. **Optimal Deliverability & Inbox Placement:**
   Major email service providers (Google Workspace, Yahoo Mail, Microsoft 365) enforce strict authentication policies. As of February 2024, unauthenticated commercial senders face automated routing to junk folders or outright SMTP drops. Passing all three checks ensures immediate inbox delivery without latency or false-positive spam flagging.
3. **Domain Reputation Preservation:**
   Cryptographically verifiable emails prevent reputation poisoning from third-party botnets attempting to masquerade as Cynbit.

---

## 5. Recommendations for Maintaining Email Authentication

Since the observed outbound email authentication for `opportunities@cynbit.in` is already properly configured, **no corrective changes or repairs are necessary for this stream**. Instead, the following maintenance best practices are recommended to sustain security:

1. **Continuous DMARC Aggregate Monitoring (`rua`):**
   Ensure an active reporting inbox or DMARC monitoring service (e.g., Postmark DMARC, Valimail, or Cloudflare DMARC Management) processes aggregate XML reports to detect unauthorized third-party senders or misaligned subdomains.
2. **Periodic DKIM Key Rotation:**
   Rotate DKIM cryptographic keys every 6 to 12 months using dual-selector staging (publish selector 2 in DNS before activating it on the MTA; retire selector 1 after a grace period). Keys should be at least 2048-bit RSA or Ed25519.
3. **Monitor the SPF 10-Lookup Limit:**
   RFC 7208 §4.6.4 limits SPF evaluation to a maximum of 10 recursive DNS lookups (`include`, `a`, `mx`, `ptr`, `exists`). As the organization adds new SaaS providers (CRM, support desk, marketing automation), periodically audit the SPF record to prevent lookup overflow errors (`PermError`).
4. **Transition to Strict DMARC Policy (`p=reject`):**
   If the organization's overarching DMARC policy is currently set to `p=none` or `p=quarantine`, evaluate aggregate reports across all operational senders to reach 100% alignment, then advance to `p=reject` for total protection against spoofing.

---

## 6. Confidence Level & Technical Limitations

- **Confidence Level:** **High** for transactional emails dispatched from `opportunities@cynbit.in`.
- **Scope Limitation:** This evaluation is based on the specific contact form response stream. It **does not assume** that all internal, marketing, or subsidiary email systems operating under `cynbit.in` or its subdomains share identical configurations.
- **DNS vs. Message Headers Distinction:**
  > [!IMPORTANT]  
  > Inspecting public DNS TXT records alone does not prove that an email has passed authentication. DNS records merely define published policy and public keys. **Actual authentication requires inspecting received RFC 5322 email headers**, which verify message-specific cryptographic signatures, sending MTA IP authorization, and identifier alignment.
