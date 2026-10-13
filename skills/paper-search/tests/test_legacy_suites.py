import selftest_connectors as connectors
import selftest_runtime as runtime


class TestConnectorHygiene(connectors.ConnectorHygieneTests):
    pass


class TestOpenAlex(connectors.OpenAlexTests):
    pass


class TestSchema(connectors.SchemaTests):
    pass


class TestArxivSchema(runtime.ArxivSchemaTests):
    pass


class TestOpenReview(runtime.OpenReviewTests):
    pass


class TestRuntime(runtime.RuntimeTests):
    pass


class TestWorker(runtime.WorkerTests):
    pass
