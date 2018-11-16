# Vault KV Helper Layer

This layer wraps [`interface:vault-kv`][interface-vault-kv] and provides a
`VaultKV` class to easily store and retrieve data from HashiCorp's [Vault][]'s
secure KV store.

# Usage

This layer adds a `vault-kv` relation endpoint to your charm.  Once Vault is
related and ready (see Flags, below), you can start using either of the KV
classes.

You can also use the flags to watch for changes to the values in the
application KV data (see Flags, below).

## Example

```python
from charms.reactive import when
from charms.layer import vault_kv


@when('layer.vault-kv.ready')
def use_vault_kv():
    unit_kv = vault_kv.VaultUnitKV()  # scoped to unit
    app_kv = vault_kv.VaultAppKV()  # shared across app

    unit_kv['foo'] = 'FOO'
    unit_kv.set('bar', {'foo': 'FOO'})
    assert unit_kv.keys() == {'foo', 'bar'}
    assert unit_kv['foo'] == 'FOO'
    assert unit_kv['bar']['foo'] = 'FOO'

    app_kv['bar'] = {'bar': 'BAR'}
    assert app_kv['bar'] != unit_kv['bar']
    assert app_kv['bar']['bar'] == 'BAR'


@when('layer.vault-kv.app-kv.changed.bar')
def notice_change():
    status.active('
```

# Flags

This layer will set the following flags:

  * `layer.vault-kv.ready` When Vault is related and ready to use

  * `layer.vault-kv.app-kv.changed` If any value in the application KV data has
    changed, whether by this or another unit.  (See [`VaultAppKV.is_changed`][].)

  * `layer.vault-kv.app-kv.changed.{key}` If the value for `{key}` in the
    application KV data has changed.

  * `layer.vault-kv.app-kv.set.{key}` If a value other than `None` is set for
    `{key}` in the application KV data.

  * `layer.vault-kv.config.changed` If the connection data has changed.

Note: None of the changed flags will be automatically removed, so it is up to
the charm to clear them, if needed.  However, to play nicely with other layers,
base layers using this may wish to [register a trigger][trigger] instead of
using the flags directly.

# Reference

More information can be found in the [documentation](docs/vault-kv.md).


[interface-vault-kv]: https://github.com/openstack-charmers/charm-interface-vault-kv
[Vault]: https://vaultproject.io/
[`VaultAppKV.is_changed`]: docs/vault-kv.md#charms.layer.vault_kv.VaultAppKV.is_changed
[trigger]: https://charmsreactive.readthedocs.io/en/latest/charms.reactive.flags.html#charms.reactive.flags.register_trigger
