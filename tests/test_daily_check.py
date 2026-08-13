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
    monkeypatch.setattr(daily_check, "_check_transient_jobs", lambda: (True, "ok"))
    rows = daily_check.run_checks(update_data=False)
    assert len(rows) == 5
    assert rows[0]["ok"] is False and "boom" in rows[0]["detail"]
    assert all(r["ok"] for r in rows[1:])


def test_parse_launchctl():
    text = ("PID\tStatus\tLabel\n"
            "72261\t0\tcom.quantbot.dryrun\n"
            "-\t75\tcom.quantbot.cnfundamentals\n"
            "-\t1\tcom.quantbot.cnroeeval\n"
            "500\t0\tcom.apple.something\n")
    jobs = daily_check.parse_launchctl(text)
    assert jobs["com.quantbot.dryrun"] == ("72261", "0")
    assert jobs["com.quantbot.cnfundamentals"] == ("-", "75")
    assert "com.apple.something" not in jobs


def test_transient_jobs_check(monkeypatch, tmp_path):
    """exit 75（限流续传）与运行中 = 正常；其他非零退出 = FAIL。"""
    log = tmp_path / "cn_fundamentals.log"
    log.write_text("login success!\n  142/1271 已落盘（累计 5485 行）\n")
    monkeypatch.setattr(daily_check, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(daily_check, "TRANSIENT_JOBS",
                        {"com.quantbot.cnfundamentals": ("A股财报下载",
                                                         "cn_fundamentals.log")})

    def fake_run(cmd, **kw):
        class R:
            stdout = "-\t75\tcom.quantbot.cnfundamentals\n"
        return R()
    monkeypatch.setattr(daily_check.subprocess, "run", fake_run)
    ok, detail = daily_check._check_transient_jobs()
    assert ok is True and "142/1271" in detail and "75" in detail

    def fake_run_bad(cmd, **kw):
        class R:
            stdout = "-\t1\tcom.quantbot.cnfundamentals\n"
        return R()
    monkeypatch.setattr(daily_check.subprocess, "run", fake_run_bad)
    ok, detail = daily_check._check_transient_jobs()
    assert ok is False and "退出码 1" in detail
