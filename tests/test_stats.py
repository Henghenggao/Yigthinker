from yigthinker.stats import StatsAccumulator


def test_increment_and_get():
    s = StatsAccumulator()
    s.increment("sql_queries_count")
    s.increment("sql_queries_count")
    assert s.get("sql_queries_count") == 2


def test_add():
    s = StatsAccumulator()
    s.add("sql_rows_scanned", 1000)
    s.add("sql_rows_scanned", 500)
    assert s.get("sql_rows_scanned") == 1500


def test_add_connection_usage():
    s = StatsAccumulator()
    s.add_connection_usage("default")
    s.add_connection_usage("default")
    s.add_connection_usage("analytics")
    assert s.get_connection_usage()["default"] == 2
    assert s.get_connection_usage()["analytics"] == 1


def test_to_dict():
    s = StatsAccumulator()
    s.increment("charts_created")
    s.add("df_rows_processed", 500)
    d = s.to_dict()
    assert d["charts_created"] == 1
    assert d["df_rows_processed"] == 500


def test_format_session_report():
    s = StatsAccumulator()
    s.increment("sql_queries_count")
    s.add("sql_rows_scanned", 1000)
    s.increment("charts_created")
    report = s.format_session_report()
    assert "SQL queries" in report
    assert "1" in report


def test_add_table_usage():
    s = StatsAccumulator()
    s.add_table_usage(["orders", "customers", "orders"])
    tables = s.to_dict()["top_tables"]
    assert tables["orders"] == 2
    assert tables["customers"] == 1
