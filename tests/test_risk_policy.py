from quantlab.risk_policy import audit_config, audit_params

COMPLIANT = {
    "stoploss": -0.08,
    "minimal_roi": {"0": 0.10, "1440": 0},
    "timeframe": "1h",
    "protections": ["CooldownPeriod", "MaxDrawdown", "StoplossGuard"],
}


def test_compliant_params_pass():
    assert audit_params("X", COMPLIANT) == []


def test_deep_stoploss_rejected():
    bad = {**COMPLIANT, "stoploss": -0.234}
    assert any("止损" in str(v) for v in audit_params("X", bad))


def test_missing_stoploss_rejected():
    bad = {**COMPLIANT, "stoploss": None}
    assert audit_params("X", bad)


def test_missing_protection_rejected():
    bad = {**COMPLIANT, "protections": ["CooldownPeriod"]}
    assert any("protections" in str(v) for v in audit_params("X", bad))


def test_bad_timeframe_rejected():
    bad = {**COMPLIANT, "timeframe": "1m"}
    assert audit_params("X", bad)


def test_config_rules():
    ok = {"dry_run": True, "max_open_trades": 3, "stake_amount": 500, "dry_run_wallet": 10000}
    assert audit_config(ok) == []
    assert audit_config({**ok, "dry_run": False})
    assert audit_config({**ok, "max_open_trades": 9})
    assert audit_config({**ok, "stake_amount": 5000})
    assert audit_config({**ok, "stake_amount": "unlimited"})
