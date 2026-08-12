import quantlab.daily_check as daily_check


def test_append_daily_log_and_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_check, "DAILY_LOG", tmp_path / "daily-log.md")
    registry = tmp_path / "run-registry.md"
    registry.write_text("| 启动时间 | 命令 | 结果 | 详情位置 |\n|---|---|---|---|\n")
    monkeypatch.setattr(daily_check, "RUN_REGISTRY", registry)

    rows = [{"name": "检查A", "ok": True, "detail": "正常"},
            {"name": "检查B", "ok": False, "detail": "异常原因"}]
    anchor = daily_check.append_daily_log(rows, "stamp-xyz")
    daily_check.append_run_registry(anchor, rows)

    log_text = (tmp_path / "daily-log.md").read_text()
    assert log_text.startswith("# 日检日志"), "首次运行自动创建带说明的文件头"
    assert f"## {anchor}" in log_text
    assert "✗ FAIL" in log_text and "异常原因" in log_text
    assert "stamp-xyz" in log_text

    registry_text = registry.read_text()
    assert f"| {anchor} | make daily | 1/2 通过 " in registry_text

    # 第二次运行：追加而非覆盖
    daily_check.append_daily_log(rows, "stamp-2")
    assert (tmp_path / "daily-log.md").read_text().count("## ") >= 2


def test_run_checks_isolates_failures(monkeypatch):
    """单项抛异常不炸整个日检，记为 FAIL 继续。"""
    monkeypatch.setattr(daily_check, "_check_bot_health",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(daily_check, "_check_paper_account", lambda: (True, "ok"))
    monkeypatch.setattr(daily_check, "_check_data_quality", lambda: (True, "ok"))
    monkeypatch.setattr(daily_check, "_check_forward_ledger", lambda: (True, "ok"))
    rows = daily_check.run_checks(update_data=False)
    assert len(rows) == 4
    assert rows[0]["ok"] is False and "boom" in rows[0]["detail"]
    assert all(r["ok"] for r in rows[1:])
