"""
Unit Tests for Email Security Monitor.

Covers:
- Valid SPF records
- Missing SPF records
- Multiple SPF records (RFC 7208 violation)
- Valid DMARC records
- Missing DMARC records
- Valid DKIM records with known selector
- Missing/Unchecked DKIM records
- DNS lookup failures (NXDOMAIN, NoAnswer, Timeout)
- Malformed DNS records (Malformed DMARC, Malformed DKIM, Permissive SPF)
- Mock DNS responses without querying external networks
"""

from unittest.mock import MagicMock
import pytest
import dns.resolver
import dns.exception

from app.security import hash_token
from email_security_monitor import (
    EmailSecurityMonitor,
    EmailSecurityReport,
    SPFReport,
    DKIMReport,
    DMARCReport,
)


class MockRdata:
    """Mock dnspython TXT rdata object."""
    def __init__(self, text: str):
        self.strings = [text.encode("utf-8")]


class MockAnswer:
    """Mock dnspython Answer object returned by resolver.resolve()."""
    def __init__(self, records):
        self._records = [MockRdata(r) if isinstance(r, str) else r for r in records]

    def __iter__(self):
        return iter(self._records)


@pytest.fixture
def mock_resolver():
    """Provides a mocked dnspython Resolver."""
    resolver = MagicMock(spec=dns.resolver.Resolver)
    return resolver


def test_valid_spf_record(mock_resolver):
    """Test 1: Valid SPF record with ~all mechanism is parsed correctly."""
    mock_resolver.resolve.return_value = MockAnswer([
        "v=spf1 include:_spf.google.com include:mailgun.org ~all"
    ])
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    report = monitor.check_spf("example.com")

    assert report.record_found is True
    assert report.status == "CONFIGURED"
    assert report.all_mechanism == "~all"
    assert len(report.warnings) == 0


def test_missing_spf_record(mock_resolver):
    """Test 2: Domain with no SPF record returns MISSING status with warning."""
    mock_resolver.resolve.side_effect = dns.resolver.NoAnswer()
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    report = monitor.check_spf("example.com")

    assert report.record_found is False
    assert report.status == "MISSING"
    assert any("direct sender address spoofing" in w for w in report.warnings)


def test_multiple_spf_records(mock_resolver):
    """Test 3: Multiple SPF records trigger RFC 7208 PermError violation."""
    mock_resolver.resolve.return_value = MockAnswer([
        "v=spf1 include:_spf.google.com ~all",
        "v=spf1 ip4:192.0.2.1 -all"
    ])
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    report = monitor.check_spf("example.com")

    assert report.record_found is True
    assert report.status == "MULTIPLE_RECORDS_ERROR"
    assert any("RFC 7208 §3.2" in w for w in report.warnings)


def test_permissive_and_oversized_spf(mock_resolver):
    """Test 4: Permissive (+all) and excessive include mechanisms generate warnings."""
    # Permissive +all
    mock_resolver.resolve.return_value = MockAnswer([
        "v=spf1 ip4:192.0.2.1 +all"
    ])
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    rep_permissive = monitor.check_spf("example.com")
    assert any("+all" in w for w in rep_permissive.warnings)

    # Excessive includes (> 10 DNS lookups)
    includes = " ".join([f"include:spf{i}.example.com" for i in range(12)])
    mock_resolver.resolve.return_value = MockAnswer([
        f"v=spf1 {includes} -all"
    ])
    rep_includes = monitor.check_spf("example.com")
    assert any("exceeding RFC 7208 maximum limit of 10" in w for w in rep_includes.warnings)


def test_valid_dmarc_record(mock_resolver):
    """Test 5: Valid DMARC record with quarantine/reject policy."""
    mock_resolver.resolve.return_value = MockAnswer([
        "v=DMARC1; p=quarantine; sp=reject; pct=100; rua=mailto:dmarc-rua@example.com"
    ])
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    report = monitor.check_dmarc("example.com")

    assert report.record_found is True
    assert report.status == "CONFIGURED"
    assert report.policy == "quarantine"
    assert report.subdomain_policy == "reject"
    assert report.percentage == 100
    assert "mailto:dmarc-rua@example.com" in report.aggregate_reports


def test_missing_dmarc_record(mock_resolver):
    """Test 6: Missing DMARC record triggers MISSING status and warning."""
    mock_resolver.resolve.side_effect = dns.resolver.NXDOMAIN()
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    report = monitor.check_dmarc("example.com")

    assert report.record_found is False
    assert report.status == "MISSING"
    assert any("No DMARC policy found" in w for w in report.warnings)


def test_malformed_dmarc_record(mock_resolver):
    """Test 7: Malformed DMARC tag structure and invalid policy values."""
    # Missing p= tag
    mock_resolver.resolve.return_value = MockAnswer(["v=DMARC1; rua=mailto:rua@example.com"])
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    rep_missing_p = monitor.check_dmarc("example.com")
    assert rep_missing_p.status == "MALFORMED"
    assert any("missing mandatory 'p='" in w for w in rep_missing_p.warnings)

    # Invalid policy value
    mock_resolver.resolve.return_value = MockAnswer(["v=DMARC1; p=drop; rua=mailto:rua@example.com"])
    rep_invalid_p = monitor.check_dmarc("example.com")
    assert rep_invalid_p.status == "MALFORMED"
    assert any("Invalid DMARC policy" in w for w in rep_invalid_p.warnings)


def test_valid_dkim_record_with_selector(mock_resolver):
    """Test 8: Valid DKIM record when selector is specified."""
    mock_resolver.resolve.return_value = MockAnswer([
        "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0exampleKey"
    ])
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    report = monitor.check_dkim("example.com", selector="google")

    assert report.record_found is True
    assert report.status == "CONFIGURED"
    assert report.selector == "google"
    assert report.key_type == "rsa"


def test_missing_and_unchecked_dkim(mock_resolver):
    """Test 9: DKIM handling when selector is omitted or missing in DNS."""
    monitor = EmailSecurityMonitor(resolver=mock_resolver)

    # No selector supplied
    rep_unspecified = monitor.check_dkim("example.com", selector=None)
    assert rep_unspecified.status == "NOT_CHECKED"
    assert rep_unspecified.record_found is False

    # Selector supplied but NXDOMAIN
    mock_resolver.resolve.side_effect = dns.resolver.NXDOMAIN()
    rep_missing = monitor.check_dkim("example.com", selector="s1")
    assert rep_missing.status == "MISSING"
    assert rep_missing.record_found is False


def test_malformed_dkim_records(mock_resolver):
    """Test 10: DKIM records with missing public key or empty revoked key."""
    # Missing public key tag p=
    mock_resolver.resolve.return_value = MockAnswer(["v=DKIM1; k=rsa;"])
    monitor = EmailSecurityMonitor(resolver=mock_resolver)
    rep_no_key = monitor.check_dkim("example.com", selector="s1")
    assert rep_no_key.status == "MALFORMED"

    # Empty public key (revoked)
    mock_resolver.resolve.return_value = MockAnswer(["v=DKIM1; k=rsa; p=;"])
    rep_revoked = monitor.check_dkim("example.com", selector="s1")
    assert rep_revoked.status == "EMPTY_KEY"


def test_dns_lookup_failures_graceful_handling(mock_resolver):
    """Test 11: Timeout and network resolution errors are captured gracefully."""
    mock_resolver.resolve.side_effect = dns.exception.Timeout("DNS server query timed out")
    monitor = EmailSecurityMonitor(resolver=mock_resolver)

    records = monitor._query_txt_records("timeout.example.com")
    assert records == []

    report = monitor.audit_domain("timeout.example.com")
    assert report.spf.status == "MISSING"
    assert report.dmarc.status == "MISSING"


def test_audit_domain_full_pipeline_and_compact_output(mock_resolver):
    """Test 12: Full domain audit output conforms to required compact JSON format."""
    def mock_resolve_side_effect(qname, rtype):
        q = str(qname)
        if q == "example.com":
            return MockAnswer(["v=spf1 include:_spf.google.com -all"])
        elif q == "_dmarc.example.com":
            return MockAnswer(["v=DMARC1; p=quarantine; rua=mailto:d@example.com"])
        elif q == "default._domainkey.example.com":
            return MockAnswer(["v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ..."])
        raise dns.resolver.NXDOMAIN()

    mock_resolver.resolve.side_effect = mock_resolve_side_effect
    monitor = EmailSecurityMonitor(resolver=mock_resolver)

    report = monitor.audit_domain("example.com", dkim_selector="default")
    assert report.overall_status == "SECURE"

    compact = report.to_compact_dict()
    assert compact["domain"] == "example.com"
    assert compact["spf"] == {"record_found": True, "status": "CONFIGURED"}
    assert compact["dkim"] == {"selector": "default", "status": "CONFIGURED"}
    assert compact["dmarc"] == {"record_found": True, "policy": "quarantine"}
