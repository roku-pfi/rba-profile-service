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


def test_the_seeded_users_are_the_tenant_cast() -> None:
    """ADR-0033 renamed the users; seeding the old `usr_demo` left Martín with
    no history, so the walkthrough's usual login scored HIGH."""
    from rba_profile_service.config import Settings
    from rba_profile_service.seed import DEFAULT_USER_ID

    assert Settings(_env_file=None).profile_seeds() == [
        ("roku-bank", "usr_rb_martin"),
        ("kaze-labs", "usr_kz_martin"),
    ]
    assert DEFAULT_USER_ID == "usr_rb_martin"


def test_a_seed_without_its_tenant_is_refused() -> None:
    """ADR-0046: a seeded history must know which tenant's population it joins."""
    import pytest

    from rba_profile_service.config import Settings

    assert Settings(_env_file=None, seed_profile_user_ids="").profile_seeds() == []
    with pytest.raises(ValueError):
        Settings(_env_file=None, seed_profile_user_ids="usr_rb_martin").profile_seeds()
