# Network & Payload Analysis

Records of observable HTTP network interactions and transactional email artifacts.

---

### 1. Initial Subscription Submission
- **Endpoint:** Public Newsletter Form (`cynbit.in`)
- **Observed Behavior:** Form accepts email and triggers transactional welcome email.
- **Email Subject:** `"Welcome to Cynbit"`
- **Body Inspection:**
  - Contains greeting and welcome text.
  - Verification URL: **Absent**
  - Unsubscribe URL: **Absent**
  - List-Unsubscribe Header: **Absent**

### 2. Duplicate Submission Analysis
- **Submitted Payload:**
  ```json
  {
    "email": "previously_registered@domain.com"
  }
  ```
- **Observed Response:**
  ```json
  {
    "success": true,
    "message": "You're already in our intelligence network!"
  }
  ```
- **Security Assessment:**
  - Indicates backend duplicate deduplication is functional.
  - Leaks user existence (user enumeration risk).
