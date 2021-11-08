from unittest.mock import patch

import pytest

from reactive.vault_kv import update_app_kv_hashes


@pytest.fixture()
def mock_vault_config():
    with patch(
        "charms.layer.vault_kv.get_vault_config",
        return_value={
            "secret_backend": "charm-unit-test",
            "vault_url": "http://vault",
            "role_id": 1234,
            "secret_id": "super-secret",
        },
    ) as vc:
        yield vc


@patch("hvac.Client", autospec=True)
@patch("charmhelpers.core.hookenv.local_unit", return_value="unit-test/0")
def test_update_app_kv_hashes(_mock_local_unit, mock_hvac_client, mock_vault_config):
    def mock_read(path):
        if path == "charm-unit-test/kv/app":
            return dict(data={"tested-key": "tested-value"})
        elif path == "charm-unit-test/kv/app-hashes/0":
            return {}

    client = mock_hvac_client.return_value
    client.read.side_effect = mock_read
    update_app_kv_hashes()
    client.write.assert_called_once_with(
        "charm-unit-test/kv/app-hashes/0",
        **{"tested-key": "b40d0066377d3ec7015ab9f498699940"}
    )
