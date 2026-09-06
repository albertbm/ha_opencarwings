# Vendored opencarwings_client

From https://github.com/developerfromjokela/opencarwings-python at commit
`75e81ec607a62e192b83347490f5d6f4c6e628fb`, copied unchanged.

Home Assistant's `is_installed()` returns False for any URL requirement, so a
git dependency is refetched on every startup and the integration fails to set
up when GitHub is slow or the network is not up yet. A vendored copy needs
neither.

Drop this directory for a normal requirement once the client reaches PyPI.

To update: copy `opencarwings_client/` again, change the commit above, run the
tests. The files are generated, so do not edit them.
