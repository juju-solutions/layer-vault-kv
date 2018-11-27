from charmhelpers.core import hookenv, host
from charms.reactive import when_all, when_not, set_flag, clear_flag
from charms.reactive import endpoint_from_flag
from charms.reactive import data_changed

from charms.layer import vault_kv


@when_all('vault-kv.connected')
@when_not('layer.vault-kv.requested')
def request_vault_access():
    vault = endpoint_from_flag('vault-kv.connected')
    # backend can't be isolated or VaultAppKV won't work; see issue #2
    vault.request_secret_backend(vault_kv._get_secret_backend(),
                                 isolated=False)
    set_flag('layer.vault-kv.requested')


@when_all('vault-kv.available')
def set_ready():
    set_flag('layer.vault-kv.ready')


@when_all('layer.vault-kv.ready')
def check_config_changed():
    config = vault_kv.get_vault_config()
    if data_changed('layer.vault-kv.config', config):
        set_flag('layer.vault-kv.config.changed')


@when_not('vault-kv.connected')
def clear_ready():
    clear_flag('layer.vault-kv.ready')
    clear_flag('layer.vault-kv.requested')


def manage_app_kv_flags():
    try:
        app_kv = vault_kv.VaultAppKV()
        for key in app_kv.keys():
            app_kv._manage_flags(key)
    except vault_kv.VaultNotReady:
        return


def update_app_kv_hashes():
    try:
        app_kv = vault_kv.VaultAppKV()
        if hookenv.is_leader() and app_kv.any_changed():
            # force hooks to run on non-leader units
            hookenv.leader_set({'vault-kv-nonce': host.pwgen(8)})
        app_kv.update_hashes()
    except vault_kv.VaultNotReady:
        return


hookenv.atstart(manage_app_kv_flags)
hookenv.atexit(update_app_kv_hashes)
