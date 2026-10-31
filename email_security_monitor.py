"""
Email Security & DNS Authentication Monitor.

Independent security module for auditing and monitoring email authentication
configurations (SPF, DKIM, DMARC) via DNS records.

Part of Cynbit Backend Technical Audit Reference Suite.
"""

from datetime import datetime, timezone
import json
import re
import sys
from typing import Any, Dict, List, Optional
import dns.resolver
import dns.exception
from pydantic import BaseModel, Field


# Regular expression patterns for authentication records
SPF_START_REGEX = re.compile(r"^v=spf1(\s|$)", re.IGNORECASE)
DMARC_START_REGEX = re.compile(r"^v=DMARC1(\s*;|$)", re.IGNORECASE)
DKIM_KEY_REGEX = re.compile(r"p=([A-Za-z0-9+/=]+)", re.IGNORECASE)


class SPFReport(BaseModel):
    """SPF (Sender Policy Framework) DNS status and policy model."""
    record_found: bool = False
    status: str = "MISSING"  # CONFIGURED, MISSING, MULTIPLE_RECORDS_ERROR, MALFORMED
    raw_record: Optional[str] = None
    all_mechanism: Optional[str] = None  # -all, ~all, ?all, +all
    warnings: List[str] = Field(default_factory=list)


class DKIMReport(BaseModel):
    """DKIM (DomainKeys Identified Mail) DNS status and public key model."""
    selector: Optional[str] = None
    record_found: bool = False
    status: str = "NOT_CHECKED"  # CONFIGURED, MISSING, MALFORMED, EMPTY_KEY, NOT_CHECKED
    raw_record: Optional[str] = None
    key_type: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class DMARCReport(BaseModel):
    """DMARC (Domain-based Message Authentication, Reporting & Conformance) model."""
    record_found: bool = False
    status: str = "MISSING"  # CONFIGURED, MISSING, MALFORMED
    policy: Optional[str] = None  # none, quarantine, reject
    percentage: Optional[int] = 100
    subdomain_policy: Optional[str] = None
    aggregate_reports: List[str] = Field(default_factory=list)
    raw_record: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class EmailSecurityReport(BaseModel):
    """Unified email security authentication report."""
    domain: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    spf: SPFReport
    dkim: DKIMReport
    dmarc: DMARCReport
    overall_status: str = "UNKNOWN"
    summary_warnings: List[str] = Field(default_factory=list)
    audit_note: str = (
        "DNS records define authorized sender policy and public keys. "
        "Actual message-level authentication (PASS/FAIL) requires inspecting "
        "received email headers (Authentication-Results, Received-SPF, DKIM-Signature) "
        "to confirm identifier alignment and cryptographic signature validity."
    )

    def to_compact_dict(self) -> Dict[str, Any]:
        """Generate compact summary output conforming to standard assessment requirements."""
        return {
            "domain": self.domain,
            "spf": {
                "record_found": self.spf.record_found,
                "status": self.spf.status
            },
            "dkim": {
                "selector": self.dkim.selector or "default",
                "status": self.dkim.status
            },
            "dmarc": {
                "record_found": self.dmarc.record_found,
                "policy": self.dmarc.policy or "none"
            }
        }


class EmailSecurityMonitor:
    """
    DNS-based Email Authentication Auditor.
    Inspects SPF, DKIM, and DMARC TXT records for syntax, compliance, and common misconfigurations.
    """

    def __init__(self, resolver: Optional[dns.resolver.Resolver] = None):
        if resolver is None:
            self.resolver = dns.resolver.Resolver()
            self.resolver.timeout = 4.0
            self.resolver.lifetime = 4.0
        else:
            self.resolver = resolver

    def _query_txt_records(self, query_name: str) -> List[str]:
        """Query DNS TXT records, concatenating multi-string TXT chunks."""
        try:
            answers = self.resolver.resolve(query_name, "TXT")
            records: List[str] = []
            for rdata in answers:
                record_text = "".join(
                    chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                    for chunk in rdata.strings
                ).strip()
                records.append(record_text)
            return records
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
            return []
        except Exception:
            return []

    def check_spf(self, domain: str) -> SPFReport:
        """
        Inspect SPF configuration for a target domain.
        RFC 7208 specifies that domains MUST NOT have more than one SPF record.
        """
        records = self._query_txt_records(domain)
        spf_records = [r for r in records if SPF_START_REGEX.search(r)]

        if not spf_records:
            return SPFReport(
                record_found=False,
                status="MISSING",
                warnings=["No SPF record found. Domain is vulnerable to direct sender address spoofing."]
            )

        if len(spf_records) > 1:
            return SPFReport(
                record_found=True,
                status="MULTIPLE_RECORDS_ERROR",
                raw_record="; ".join(spf_records),
                warnings=[
                    f"Found {len(spf_records)} SPF records. RFC 7208 §3.2 strictly forbids multiple "
                    "SPF records; receiving MTAs will return a PermError, failing authentication."
                ]
            )

        raw = spf_records[0]
        warnings = []
        all_mech = None

        all_match = re.search(r"(\+|-|~|\?)all\b", raw, re.IGNORECASE)
        if all_match:
            all_mech = all_match.group(1).lower() + "all"
            if all_mech == "+all":
                warnings.append("SPF record ends with '+all' (allow all), effectively disabling spoofing protection.")
            elif all_mech == "?all":
                warnings.append("SPF record uses '?all' (neutral), providing no definitive spoofing enforcement.")
        else:
            warnings.append("SPF record does not specify an explicit default mechanism (e.g. -all or ~all).")

        include_count = len(re.findall(r"\binclude:", raw, re.IGNORECASE))
        if include_count > 10:
            warnings.append(
                f"SPF record contains {include_count} 'include' mechanisms. Risk of exceeding "
                "RFC 7208 maximum limit of 10 DNS lookups (PermError)."
            )

        return SPFReport(
            record_found=True,
            status="CONFIGURED",
            raw_record=raw,
            all_mechanism=all_mech,
            warnings=warnings
        )

    def check_dkim(self, domain: str, selector: Optional[str] = None) -> DKIMReport:
        """
        Inspect DKIM public key record at <selector>._domainkey.<domain>.
        """
        if not selector:
            return DKIMReport(
                selector=None,
                record_found=False,
                status="NOT_CHECKED",
                warnings=["DKIM selector not specified. DKIM record cannot be queried without a known selector."]
            )

        query_name = f"{selector}._domainkey.{domain}"
        records = self._query_txt_records(query_name)

        if not records:
            return DKIMReport(
                selector=selector,
                record_found=False,
                status="MISSING",
                warnings=[f"No DKIM record found at {query_name} for selector '{selector}'."]
            )

        raw = records[0]
        warnings = []

        tags: Dict[str, str] = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                tags[k.strip().lower()] = v.strip()

        key_value = tags.get("p")
        key_type = tags.get("k", "rsa")

        if key_value == "":
            return DKIMReport(
                selector=selector,
                record_found=True,
                status="EMPTY_KEY",
                raw_record=raw,
                key_type=key_type,
                warnings=[f"DKIM public key is empty at {query_name}. Signifies revoked key."]
            )
        elif not key_value:
            return DKIMReport(
                selector=selector,
                record_found=True,
                status="MALFORMED",
                raw_record=raw,
                warnings=[f"DKIM record at {query_name} is missing required 'p=' public key tag."]
            )

        return DKIMReport(
            selector=selector,
            record_found=True,
            status="CONFIGURED",
            raw_record=raw,
            key_type=key_type,
            warnings=warnings
        )

    def check_dmarc(self, domain: str) -> DMARCReport:
        """
        Inspect DMARC policy record at _dmarc.<domain>.
        """
        query_name = f"_dmarc.{domain}"
        records = self._query_txt_records(query_name)
        dmarc_records = [r for r in records if DMARC_START_REGEX.search(r)]

        if not dmarc_records:
            return DMARCReport(
                record_found=False,
                status="MISSING",
                warnings=["No DMARC policy found. Domain lacks policy enforcement and feedback reporting."]
            )

        raw = dmarc_records[0]
        warnings = []

        tags: Dict[str, str] = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                tags[k.strip().lower()] = v.strip()

        policy = tags.get("p", "").lower()
        subdomain_policy = tags.get("sp", "").lower() if "sp" in tags else None
        pct = int(tags.get("pct", 100)) if tags.get("pct", "").isdigit() else 100

        rua_raw = tags.get("rua", "")
        rua_list = [addr.strip() for addr in rua_raw.split(",") if addr.strip()]

        if not policy:
            return DMARCReport(
                record_found=True,
                status="MALFORMED",
                raw_record=raw,
                warnings=["DMARC record is missing mandatory 'p=' policy tag."]
            )

        if policy not in ["none", "quarantine", "reject"]:
            return DMARCReport(
                record_found=True,
                status="MALFORMED",
                raw_record=raw,
                warnings=[f"Invalid DMARC policy 'p={policy}'. Must be 'none', 'quarantine', or 'reject'."]
            )

        if policy == "none":
            warnings.append("DMARC policy is set to 'p=none' (monitoring only). Spoofed messages will still be delivered.")

        if pct < 100:
            warnings.append(f"DMARC policy percentage is set to {pct}%, leaving {100-pct}% of messages uninspected.")

        if not rua_list:
            warnings.append("DMARC record does not specify aggregate reporting ('rua='). Visibility into spoofing is limited.")

        return DMARCReport(
            record_found=True,
            status="CONFIGURED",
            policy=policy,
            percentage=pct,
            subdomain_policy=subdomain_policy,
            aggregate_reports=rua_list,
            raw_record=raw,
            warnings=warnings
        )

    def audit_domain(self, domain: str, dkim_selector: Optional[str] = None) -> EmailSecurityReport:
        """
        Execute full email authentication audit for a domain.
        """
        clean_domain = domain.strip().lower()
        spf_rep = self.check_spf(clean_domain)
        dkim_rep = self.check_dkim(clean_domain, dkim_selector)
        dmarc_rep = self.check_dmarc(clean_domain)

        all_warnings: List[str] = []
        all_warnings.extend(spf_rep.warnings)
        all_warnings.extend(dkim_rep.warnings)
        all_warnings.extend(dmarc_rep.warnings)

        if spf_rep.status == "CONFIGURED" and dmarc_rep.status == "CONFIGURED":
            if dkim_rep.status in ["CONFIGURED", "NOT_CHECKED"]:
                overall = "SECURE" if dmarc_rep.policy in ["quarantine", "reject"] else "MONITORING_ONLY"
            else:
                overall = "NEEDS_ATTENTION"
        elif spf_rep.status == "MULTIPLE_RECORDS_ERROR" or dmarc_rep.status == "MALFORMED":
            overall = "MISCONFIGURED"
        else:
            overall = "INCOMPLETE"

        return EmailSecurityReport(
            domain=clean_domain,
            spf=spf_rep,
            dkim=dkim_rep,
            dmarc=dmarc_rep,
            overall_status=overall,
            summary_warnings=all_warnings
        )


def main():
    """Command-line interface for email authentication monitoring."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Audit domain email authentication records (SPF, DKIM, DMARC)."
    )
    parser.add_argument("domain", help="Target domain (e.g., cynbit.in)")
    parser.add_argument(
        "--selector", "-s",
        help="Optional DKIM selector to query (e.g., google, default, cynbit)"
    )
    parser.add_argument(
        "--compact", "-c",
        action="store_true",
        help="Output minimal JSON conforming to assessment specification"
    )
    parser.add_argument(
        "--indent", "-i",
        type=int,
        default=2,
        help="JSON indentation (default: 2)"
    )

    args = parser.parse_args()

    monitor = EmailSecurityMonitor()
    report = monitor.audit_domain(domain=args.domain, dkim_selector=args.selector)

    if args.compact:
        print(json.dumps(report.to_compact_dict(), indent=args.indent))
    else:
        print(json.dumps(report.model_dump(mode="json"), indent=args.indent))


if __name__ == "__main__":
    main()
