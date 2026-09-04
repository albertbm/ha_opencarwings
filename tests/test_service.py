import pytest

import custom_components.ha_opencarwings as init_mod
from conftest import run_executor, stub_client


class ServicesStub:
    def __init__(self):
        self._handlers = {}

    def async_register(self, domain, service, handler):
        self._handlers[(domain, service)] = handler

    async def async_call(self, domain, service, data=None):
        handler = self._handlers.get((domain, service))
        if handler:
            class Call:
                def __init__(self, data):
                    self.data = data

            await handler(Call(data or {}))


@pytest.mark.asyncio
async def test_refresh_service_for_entry(monkeypatch):
    # Create a fake coordinator that records refresh calls
    class FakeCoordinator:
        def __init__(self):
            self.called = False

        async def async_request_refresh(self):
            self.called = True

    coord = FakeCoordinator()

    class C:
        async def async_forward_entry_setups(self, *args, **kwargs):
            return None

    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": coord}}}, "services": ServicesStub(), "config_entries": C()})()
    hass.async_add_executor_job = run_executor

    class FakeCoordinatorClass:
        def __init__(self, hass, logger, name, update_method, update_interval=None):
            self.called = False
            self.update_method = update_method
            self.data = []

        async def async_config_entry_first_refresh(self):
            self.data = await self.update_method()

        async def async_request_refresh(self):
            self.called = True

    stub_client(monkeypatch)
    monkeypatch.setattr(init_mod, "DataUpdateCoordinator", FakeCoordinatorClass)

    entry = type("E", (), {"entry_id": "e1", "title": "e1", "data": {"api_key": "k"}})()
    # call setup which should register service
    await init_mod.async_setup_entry(hass, entry)

    # find the coordinator instance installed by setup
    real_coord = hass.data["ha_opencarwings"]["e1"].get("coordinator")

    # call the service targeting entry e1
    await hass.services.async_call("ha_opencarwings", "refresh", {"entry_id": "e1"})

    assert getattr(real_coord, "called", False) is True


@pytest.mark.asyncio
async def test_refresh_service_refreshes_all(monkeypatch):
    class FakeCoordinator:
        def __init__(self):
            self.called = False

        async def async_request_refresh(self):
            self.called = True

    c1 = FakeCoordinator()
    c2 = FakeCoordinator()

    class C:
        async def async_forward_entry_setups(self, *args, **kwargs):
            return None

    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": c1}, "e2": {"coordinator": c2}}}, "services": ServicesStub(), "config_entries": C()})()
    hass.async_add_executor_job = run_executor

    class FakeCoordinatorClass:
        def __init__(self, hass, logger, name, update_method, update_interval=None):
            self.called = False
            self.update_method = update_method
            self.data = []

        async def async_config_entry_first_refresh(self):
            self.data = await self.update_method()

        async def async_request_refresh(self):
            self.called = True

    stub_client(monkeypatch)
    monkeypatch.setattr(init_mod, "DataUpdateCoordinator", FakeCoordinatorClass)

    entry = type("E", (), {"entry_id": "e1", "title": "e1", "data": {"api_key": "k"}})()
    await init_mod.async_setup_entry(hass, entry)

    await hass.services.async_call("ha_opencarwings", "refresh", {})

    # the installed coordinators were created by setup; ensure both were called
    assert hass.data["ha_opencarwings"]["e1"]["coordinator"].called is True
    assert hass.data["ha_opencarwings"]["e2"]["coordinator"].called is True