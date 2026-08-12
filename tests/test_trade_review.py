from quantlab.trade_review import aggregate_trades


def make_trade(pair="BTC/USDT", profit_ratio=0.01, profit_abs=5.0,
               exit_reason="roi", duration=120, open_date="2025-01-01 00:00:00+00:00"):
    return {
        "pair": pair, "profit_ratio": profit_ratio, "profit_abs": profit_abs,
        "exit_reason": exit_reason, "trade_duration": duration, "open_date": open_date,
    }


TRADES = [
    make_trade(profit_ratio=0.02, profit_abs=10, exit_reason="roi", duration=60),
    make_trade(profit_ratio=0.04, profit_abs=20, exit_reason="roi", duration=100,
               pair="ETH/USDT"),
    make_trade(profit_ratio=-0.08, profit_abs=-40, exit_reason="stop_loss", duration=300),
    make_trade(profit_ratio=-0.01, profit_abs=-5, exit_reason="exit_signal", duration=200,
               pair="ETH/USDT"),
]


def test_aggregate_basics():
    stats = aggregate_trades(TRADES)
    assert stats["n"] == 4
    assert stats["wins"] == 2
    assert abs(stats["winrate"] - 0.5) < 1e-9
    assert abs(stats["total_profit_abs"] - (-15.0)) < 1e-9


def test_aggregate_by_exit_reason():
    stats = aggregate_trades(TRADES)
    roi = stats["by_exit_reason"]["roi"]
    assert roi["n"] == 2 and abs(roi["total_abs"] - 30.0) < 1e-9
    assert stats["by_exit_reason"]["stop_loss"]["n"] == 1


def test_aggregate_durations_and_extremes():
    stats = aggregate_trades(TRADES)
    assert abs(stats["avg_duration_win_min"] - 80) < 1e-9
    assert abs(stats["avg_duration_loss_min"] - 250) < 1e-9
    assert stats["worst"][0]["profit_ratio"] == -0.08
    assert stats["best"][0]["profit_ratio"] == 0.04


def test_aggregate_empty():
    stats = aggregate_trades([])
    assert stats["n"] == 0 and stats["winrate"] == 0.0
