"""Unit tests for AVEVA database driver."""

import json
import os
import unittest

from gemini.core.data.connector.avevadb_driver import AvevaDriver


class TestAVEVADB(unittest.TestCase):
    """Test cases for AVEVA database driver."""

    def test_connection(self):
        """Test AVEVA database connection."""
        db_driver = AvevaDriver()
        parameters = dict()

        credentials_name = os.path.join(
            os.getcwd(), "unit_test", "database", "credentials", "avevadb.json"
        )
        if os.path.isfile(credentials_name):
            with open(credentials_name) as f:
                config = json.load(f)

            parameters["api_version"] = config["ApiVersion"]
            parameters["url"] = config["url"]
            parameters["tenant"] = config["TenantId"]
            parameters["namespace_id"] = config["NamespaceId"]
            parameters["client_id"] = config["ClientId"]
            parameters["client_secret"] = config["ClientSecret"]

            parameters["interval"] = 300

            db_driver.update_parameters(parameters)

            db_driver.connect()

            db_driver.check_query()

        else:
            print("No credentials file. Did not test the connection")
