import asyncio

import pytest

from conftest import make_car

from custom_components.ha_opencarwings import commands


class FakeCoordinator:
    def __init__(self):
        self.refreshes = 0

    async def async_request_refresh(self):
        self.refreshes += 1


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event, data):
        self.events.append((event, data))


class FakeClient:
    """Serves a queue of car states, repeating the last one."""

    def __init__(self, states):
        self.states = list(states)
        self.reads = 0

    def install(self, monkeypatch):
        import opencarwings_client

        client = self

        class _CarsApi:
            def __init__(self, _):
                pass

            async def api_car_read(self, vin):
                client.reads += 1
                if len(client.states) > 1:
                    return client.states.pop(0)
                return client.states[0]

        monkeypatch.setattr(opencarwings_client, "CarsApi", _CarsApi)
        return self


def _hass(client, coordinator, bus):
    tasks = []

    class H:
        data = {"ha_opencarwings": {"e1": {"client": client, "coordinator": coordinator}}}

        def async_create_task(self, coro, name=None):
            task = asyncio.get_event_loop().create_task(coro)
            tasks.append(task)
            return task

    h = H()
    h.bus = bus
    h.config_entries = type("C", (), {"async_get_entry": lambda self, e: None})()
    h.tasks = tasks
    return h


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    # Poll immediately, but keep interval and timeout in proportion.
    monkeypatch.setattr(commands, "POLL_INTERVAL", 0.001)
    monkeypatch.setattr(commands, "POLL_TIMEOUT", 0.03)


def _pending():
    return make_car(vin="VIN1", command_requested=True,
                    command_result=commands.RESULT_AWAIT_RESPONSE).get_latest_car()


def _done(result):
    return make_car(vin="VIN1", command_requested=False,
                    command_result=result).get_latest_car()


@pytest.mark.asyncio
async def test_watch_waits_for_the_car_then_refreshes(monkeypatch):
    client = FakeClient([_pending(), _pending(), _done(commands.RESULT_SUCCESS)]).install(monkeypatch)
    coord, bus = FakeCoordinator(), FakeBus()
    hass = _hass(client, coord, bus)

    commands._start_result_watch(hass, "e1", "VIN1", commands.CMD_AC_ON, "turn the A/C on")
    await asyncio.gather(*hass.tasks)

    assert client.reads == 3
    assert coord.refreshes == 1
    assert bus.events[0][0] == "ha_opencarwings_command_finished"
    assert bus.events[0][1]["result"] == "success"
    assert bus.events[0][1]["vin"] == "VIN1"


@pytest.mark.asyncio
async def test_a_failed_command_is_reported_as_error(monkeypatch):
    client = FakeClient([_done(commands.RESULT_ERROR)]).install(monkeypatch)
    coord, bus = FakeCoordinator(), FakeBus()
    hass = _hass(client, coord, bus)

    commands._start_result_watch(hass, "e1", "VIN1", commands.CMD_AC_ON, "turn the A/C on")
    await asyncio.gather(*hass.tasks)

    assert bus.events[0][1]["result"] == "error"


@pytest.mark.asyncio
async def test_a_car_that_never_answers_gives_up_at_the_server_timeout(monkeypatch):
    client = FakeClient([_pending()]).install(monkeypatch)
    coord, bus = FakeCoordinator(), FakeBus()
    hass = _hass(client, coord, bus)

    commands._start_result_watch(hass, "e1", "VIN1", commands.CMD_AC_ON, "turn the A/C on")
    await asyncio.gather(*hass.tasks)

    assert bus.events[0][1]["result"] == "timeout"
    assert coord.refreshes == 1


@pytest.mark.asyncio
async def test_one_watcher_per_car(monkeypatch):
    client = FakeClient([_pending(), _done(commands.RESULT_SUCCESS)]).install(monkeypatch)
    hass = _hass(client, FakeCoordinator(), FakeBus())

    commands._start_result_watch(hass, "e1", "VIN1", commands.CMD_AC_ON, "turn the A/C on")
    commands._start_result_watch(hass, "e1", "VIN1", commands.CMD_AC_OFF, "turn the A/C off")

    assert len(hass.tasks) == 1
    await asyncio.gather(*hass.tasks)
    # The slot frees up once the command resolves.
    assert hass.data["ha_opencarwings"]["_watching"] == set()


@pytest.mark.asyncio
async def test_read_failures_do_not_end_the_watch(monkeypatch):
    import opencarwings_client

    client = FakeClient([_pending()])

    class _CarsApi:
        def __init__(self, _):
            pass

        async def api_car_read(self, vin):
            client.reads += 1
            if client.reads == 1:
                raise RuntimeError("network")
            return _done(commands.RESULT_SUCCESS)

    monkeypatch.setattr(opencarwings_client, "CarsApi", _CarsApi)
    coord, bus = FakeCoordinator(), FakeBus()
    hass = _hass(client, coord, bus)

    commands._start_result_watch(hass, "e1", "VIN1", commands.CMD_AC_ON, "turn the A/C on")
    await asyncio.gather(*hass.tasks)

    assert client.reads == 2
    assert bus.events[0][1]["result"] == "success"
