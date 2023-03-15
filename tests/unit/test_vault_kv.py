from unittest import mock

import pytest
import hvac.exceptions

from charms.layer.vault_kv import get_vault_config, VaultNotReady
from charms.reactive import endpoint_from_flag, is_data_changed, data_changed
from charmhelpers.core import unitdata, hookenv


@pytest.fixture()
def vault():
    """Mock vault kv endpoint"""
    vault = endpoint_from_flag("vault-kv.available")
    vault.vault_url = "https://test.me:4040"
    vault.unit_role_id = "test-role-id"
    vault.unit_token = "some-secret-token-value"
    hookenv.application_name.return_value = "my-juju-app"
    is_data_changed.return_value = True

    yield vault

    hookenv.application_name.reset_mock()
    data_changed.reset_mock()
    is_data_changed.reset_mock()


@mock.patch("charms.layer.vault_kv.retrieve_secret_id")
def test_get_vault_config_success(mock_rtv_secret_id, vault):
    """Confirm vault config can be retrieved with valid relation data."""

    with mock.patch.object(
        unitdata.kv.return_value, "flush", create=True
    ) as mock_flush:
        mock_rtv_secret_id.return_value = "secret-from-token-value"
        vault_config = get_vault_config()

    mock_rtv_secret_id.assert_called_once_with(vault.vault_url, vault.unit_token)
    data_changed.assert_called_once_with("layer.vault-kv.token", vault.unit_token)
    mock_flush.assert_called_once_with()
    assert vault_config == {
        "vault_url": vault.vault_url,
        "secret_backend": f"charm-{hookenv.application_name.return_value}",
        "role_id": vault.unit_role_id,
        "secret_id": "secret-from-token-value",
    }


@mock.patch("charms.layer.vault_kv.retrieve_secret_id")
def test_get_vault_config_fails_get_secret_id(mock_rtv_secret_id, vault):
    """
    Confirm vault failures transitions to VaultNotReady.

    Also confirm the kv storage and data_changed hash is only updated on
    successful retrieval using the one-time token from `secret_id`
    """
    mock_rtv_secret_id.side_effect = hvac.exceptions.VaultDown()
    with pytest.raises(VaultNotReady):
        get_vault_config()

    is_data_changed.assert_called_once_with("layer.vault-kv.token", vault.unit_token)
    mock_rtv_secret_id.assert_called_once_with(vault.vault_url, vault.unit_token)
    data_changed.assert_not_called()
