"""Boundary tests for the pure image fetch policy.

Assumed public interface of ``web_to_epub.core.image_policy``:

- ``Verdict``: has boolean ``allowed`` and string ``reason``
- ``DEFAULT_MAX_BYTES``: 10 MB (10 * 1024 * 1024)
- ``check_url(url: str) -> Verdict``: scheme, credentials, IP-literal hosts
- ``check_address(address: str) -> Verdict``: an already-resolved IP address
- ``check_response(content_type: str | None, size: int, max_bytes=DEFAULT_MAX_BYTES) -> Verdict``
"""

import ipaddress

import pytest
from hypothesis import given, strategies as st

from web_to_epub.core.image_policy import (
    DEFAULT_MAX_BYTES,
    check_address,
    check_response,
    check_url,
)

# --- URL: scheme -----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/a.png",
        "data:image/png;base64,iVBORw0KGgo=",
        "javascript:alert(1)",
        "gopher://example.com/a.png",
        "//example.com/a.png",
        "not a url",
        "",
    ],
)
def test_non_http_schemes_are_rejected(url):
    assert not check_url(url).allowed


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a.png",
        "https://example.com/images/a.jpg?w=200",
        "https://cdn.example.org:8443/x/y.gif",
        "HTTPS://Example.com/A.PNG",
        "http://93.184.216.34/a.png",
        "https://[2606:2800:220:1:248:1893:25c8:1946]/a.png",
    ],
)
def test_ordinary_public_http_urls_are_accepted(url):
    verdict = check_url(url)
    assert verdict.allowed, verdict.reason


# --- URL: credentials ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com/a.png",
        "http://user@example.com/a.png",
        "http://:pass@example.com/a.png",
        "https://example.com@evil.example.net/a.png",
    ],
)
def test_urls_with_embedded_credentials_are_rejected(url):
    assert not check_url(url).allowed


# --- URL: IP-literal hosts -------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a.png",
        "http://127.1.2.3:8080/a.png",
        "http://10.0.0.5/a.png",
        "http://172.16.0.1/a.png",
        "http://172.31.255.255/a.png",
        "http://192.168.1.1/a.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/a.png",
        "http://0.0.0.0/a.png",
        "http://[::1]/a.png",
        "http://[::]/a.png",
        "http://[fe80::1]/a.png",
        "http://[fc00::1]/a.png",
        "http://[fd12:3456::1]/a.png",
        "http://[::ffff:127.0.0.1]/a.png",
        "http://[::ffff:10.0.0.1]/a.png",
        "http://[::ffff:169.254.169.254]/a.png",
        "http://[::ffff:7f00:1]/a.png",
    ],
)
def test_urls_with_private_ip_hosts_are_rejected(url):
    assert not check_url(url).allowed


def test_metadata_ip_url_is_rejected():
    verdict = check_url("http://169.254.169.254/latest/meta-data/iam/")
    assert verdict.allowed is False
    assert verdict.reason


# --- Resolved addresses ----------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.255.255.254",
        "10.1.2.3",
        "172.16.5.5",
        "192.168.0.10",
        "169.254.169.254",
        "169.254.0.1",
        "0.0.0.0",
        "::1",
        "::",
        "fe80::abcd",
        "fc00::1",
        "fd00::1234",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:192.168.1.1",
        "::ffff:169.254.169.254",
        "::ffff:0.0.0.0",
    ],
)
def test_private_and_reserved_addresses_are_rejected(address):
    assert not check_address(address).allowed


@pytest.mark.parametrize(
    "address",
    [
        "93.184.216.34",
        "8.8.8.8",
        "1.1.1.1",
        "172.32.0.1",
        "2606:2800:220:1:248:1893:25c8:1946",
        "2001:4860:4860::8888",
        "::ffff:8.8.8.8",
    ],
)
def test_public_addresses_are_accepted(address):
    verdict = check_address(address)
    assert verdict.allowed, verdict.reason


def test_unparseable_address_is_rejected():
    assert not check_address("not-an-ip").allowed


# --- Response policy -------------------------------------------------------


def test_default_cap_is_ten_megabytes():
    assert DEFAULT_MAX_BYTES == 10 * 1024 * 1024


def test_response_within_cap_and_image_type_is_accepted():
    verdict = check_response("image/png", 1024)
    assert verdict.allowed, verdict.reason


def test_response_exactly_at_default_cap_is_accepted():
    assert check_response("image/jpeg", DEFAULT_MAX_BYTES).allowed


def test_response_over_default_cap_is_rejected():
    assert not check_response("image/jpeg", DEFAULT_MAX_BYTES + 1).allowed


def test_content_type_parameters_and_case_are_tolerated():
    assert check_response("Image/PNG; charset=binary", 100).allowed


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "application/json", "application/octet-stream", "", None, "imagex/png"],
)
def test_non_image_content_types_are_rejected(content_type):
    assert not check_response(content_type, 100).allowed


def test_cap_is_configurable_lower():
    assert not check_response("image/png", 501, max_bytes=500).allowed
    assert check_response("image/png", 500, max_bytes=500).allowed


def test_cap_is_configurable_higher():
    size = DEFAULT_MAX_BYTES + 1
    assert check_response("image/png", size, max_bytes=size).allowed


# --- Properties ------------------------------------------------------------

_PRIVATE_V4_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
    )
]
_PRIVATE_V6_NETS = [
    ipaddress.ip_network(n) for n in ("::1/128", "::/128", "fc00::/7", "fe80::/10")
]


def _addr_in(net):
    return st.integers(
        min_value=int(net.network_address), max_value=int(net.broadcast_address)
    ).map(lambda i: ipaddress.ip_address(i))


private_v4 = st.one_of(*[_addr_in(n) for n in _PRIVATE_V4_NETS])
private_v6 = st.one_of(*[_addr_in(n) for n in _PRIVATE_V6_NETS])


@given(private_v4)
def test_property_any_private_ipv4_is_rejected(ip):
    assert not check_address(str(ip)).allowed


@given(private_v6)
def test_property_any_private_ipv6_is_rejected(ip):
    assert not check_address(str(ip)).allowed


@given(private_v4)
def test_property_ipv4_mapped_private_is_rejected(ip):
    mapped = ipaddress.IPv6Address(f"::ffff:{ip}")
    assert not check_address(str(mapped)).allowed


@given(private_v4)
def test_property_private_ipv4_literal_urls_are_rejected(ip):
    assert not check_url(f"http://{ip}/a.png").allowed


@given(st.integers(min_value=0, max_value=100 * 1024 * 1024), st.integers(min_value=1, max_value=50 * 1024 * 1024))
def test_property_size_accepted_iff_within_cap(size, cap):
    assert check_response("image/png", size, max_bytes=cap).allowed == (size <= cap)
