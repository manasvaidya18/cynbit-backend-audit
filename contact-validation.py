#!/usr/bin/env python3
"""
CLI & Service Runner for Cynbit Contact Validation Reference Implementation.
Directs execution to contact_validation module.
"""

from contact_validation import (
    app,
    ContactRequest,
    ContactResponse,
    ContactSubmission,
    contact_email_service,
    contact_rate_limiter,
)

if __name__ == "__main__":
    import uvicorn
    print("Starting Cynbit Contact Validation Service on http://127.0.0.1:8002")
    uvicorn.run(app, host="127.0.0.1", port=8002)
