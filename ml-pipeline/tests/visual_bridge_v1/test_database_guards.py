import json

import pytest

from integration.visual_bridge_v1.catalogue import ReadOnlyCatalogue, snapshot_sql
from integration.visual_bridge_v1.errors import BridgeError
from sahulat_database.migrations import run_psql
from tests.visual_bridge_v1.test_catalogue import search

pytestmark = pytest.mark.database


def test_admin_config_cannot_become_bridge_application_account(migrated_database):
    assert migrated_database.config.user == "postgres"
    with pytest.raises(BridgeError, match="database_permission_rejected"):
        ReadOnlyCatalogue(migrated_database.config)


def test_permission_sql_compiles_and_admin_branch_does_not_read_catalog(migrated_database):
    # Administrative syntax/guard diagnostic, NOT an application-role integration smoke.
    # The SQL returns permission rejection without entering its business-data branch.
    output = run_psql(
        migrated_database.config, stdin_sql=snapshot_sql(migrated_database.config, search())
    ).stdout
    records = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    assert records == [{"permission_ok": False, "rows": []}]
