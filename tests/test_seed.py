"""Home-profile seed for Demo-2 (no Redis required)."""

from rba_profile_service.seed import HOME_ASN, HOME_COUNTRY, HOME_IP, build_home_profile


def test_home_profile_looks_usual() -> None:
    profile = build_home_profile()
    assert profile.login_count >= 20
    assert profile.last_login_country == HOME_COUNTRY
    assert HOME_IP in profile.seen_ips
    assert HOME_ASN in profile.seen_asns
    assert HOME_COUNTRY in profile.seen_countries
    assert "desktop" in profile.seen_device_types
    assert profile.freeman_total("country") == profile.login_count
    assert profile.freeman_count("country", HOME_COUNTRY) == profile.login_count
