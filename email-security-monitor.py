#!/usr/bin/env python3
"""
CLI entrypoint wrapper for Email Security & DNS Authentication Monitor.
Directs execution to email_security_monitor module.
"""

from email_security_monitor import (
    main,
    EmailSecurityMonitor,
    EmailSecurityReport,
    SPFReport,
    DKIMReport,
    DMARCReport,
)

if __name__ == "__main__":
    main()
