from unittest import mock

import pytest
import hvac.exceptions

from charms.layer.vault_kv import (
    get_vault_config,
    VaultAppKV,
    VaultNotReady,
    VaultUnitKV,
)
from charms.reactive import endpoint_from_flag, is_data_changed, data_changed
from charmhelpers.core import unitdata, hookenv


@pytest.fixture(autouse=True)
def vault():
    """Mock vault kv endpoint"""
    endpoint = endpoint_from_flag("vault-kv.available")
    endpoint.vault_url = "https://test.me:4040"
    endpoint.unit_role_id = "test-role-id"
    endpoint.unit_token = "some-secret-token-value"
    hookenv.application_name.return_value = "my-juju-app"
    hookenv.model_uuid.return_value = "11111111-2222-3333-4444-555555555555"
    is_data_changed.return_value = True

    yield endpoint

    hookenv.application_name.reset_mock()
    hookenv.model_uuid.reset_mock()
    data_changed.reset_mock()
    is_data_changed.reset_mock()


@pytest.fixture(params=["", "charm-{app}", "charm-{model-uuid}-{app}"])
def backend_format(request):
    class Formatter(str):
        @property
        def expected(self):
            fmt = self
            if fmt == "":
                fmt = "charm-{app}"
            context = {
                "model-uuid": hookenv.model_uuid.return_value,
                "app": hookenv.application_name.return_value,
            }
            return fmt.format(**context)

    yield Formatter(request.param)
    hookenv.application_name.assert_called_once_with()
    hookenv.model_uuid.assert_called_once_with()


@mock.patch("charms.layer.vault_kv.retrieve_secret_id")
def test_get_vault_config_success(mock_rtv_secret_id, vault, backend_format):
    """Confirm vault config can be retrieved with valid relation data."""

    with mock.patch.object(
        unitdata.kv.return_value, "flush", create=True
    ) as mock_flush:
        mock_rtv_secret_id.return_value = "secret-from-token-value"
        vault_config = get_vault_config(backend_format=backend_format)

    mock_rtv_secret_id.assert_called_once_with(vault.vault_url, vault.unit_token)
    data_changed.assert_called_once_with("layer.vault-kv.token", vault.unit_token)
    mock_flush.assert_called_once_with()
    assert vault_config == {
        "vault_url": vault.vault_url,
        "secret_backend": backend_format.expected,
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


@mock.patch("hvac.Client", autospec=True)
@mock.patch("charms.layer.vault_kv.retrieve_secret_id")
def test_vault_app_kv_singleton(mock_rtv_secret_id, mock_client, backend_format):
    mock_client().read.return_value = dict(data={})
    with mock.patch.object(
        unitdata.kv.return_value, "flush", create=True
    ) as mock_flush:
        mock_rtv_secret_id.return_value = "secret-from-token-value"

        kv = VaultAppKV(backend_format=backend_format)
        kv2 = VaultAppKV()

    assert kv is kv2, "Should be singleton instances"
    assert kv._config["secret_backend"] == backend_format.expected

    # Nothing yet set
    assert kv.keys() == set()
    mock_client().write.assert_not_called()

    kv["settable"] = "value"
    mock_client().write.assert_called_once_with(
        f"{backend_format.expected}/kv/app", settable="value"
    )
    mock_client().write.reset_mock()

    kv.set("settable", "new-value")
    mock_client().write.assert_called_once_with(
        f"{backend_format.expected}/kv/app", settable="new-value"
    )

    assert dict(kv.items()) == {"settable": "new-value"}
