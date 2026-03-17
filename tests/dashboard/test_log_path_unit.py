from relace_dashboard.log_reader import get_log_path


class TestDashboardLogPath:
    def test_default_platformdirs(self) -> None:
        result = get_log_path()
        assert result.name == "relace.log"
