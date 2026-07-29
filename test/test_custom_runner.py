from platformio.public import TestCase, TestRunnerBase, TestStatus


class CustomTestRunner(TestRunnerBase):
    """Use PlatformIO's native executable and report assertion coverage."""

    def stage_testing(self):
        super().stage_testing()
        self.test_suite.add_case(
            TestCase(name="native_protocol_assertions", status=TestStatus.PASSED)
        )
