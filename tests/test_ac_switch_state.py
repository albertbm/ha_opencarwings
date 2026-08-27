import pytest

from custom_components.ha_opencarwings import switch as switch_mod
from custom_components.ha_opencarwings.commands import CMD_AC_ON


class FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self.last_update_success = True

    def async_add_listener(self, *args, **kwargs):
        return lambda: None


def _car(ac_status):
    return {"vin": "VIN1", "nickname": "DKL", "model_name": "Leaf",
            "ev_info": {"id": 1, "ac_status": ac_status}}


def _switch(ac_status):
    coordinator = FakeCoordinator([_car(ac_status)])
    sw = switch_mod.CarClimateSwitch(coordinator, "e1", _car(ac_status))
    sw.hass = type("H", (), {"bus": None})()
    return coordinator, sw


def test_reports_server_status():
    _, sw = _switch(True)
    assert sw.is_on is True
    assert sw._attr_translation_key == "climate"


def test_unknown_without_ev_info():
    coordinator = FakeCoordinator([{"vin": "VIN1"}])
    sw = switch_mod.CarClimateSwitch(coordinator, "e1", {"vin": "VIN1"})
    assert sw.is_on is None


@pytest.mark.asyncio
async def test_pending_holds_until_server_agrees(monkeypatch):
    coordinator, sw = _switch(False)
    monkeypatch.setattr(sw, "async_write_ha_state", lambda: None)

    sent = []
    async def fake_send(hass, entry_id, vin, cmd, desc, **kw):
        sent.append(cmd)
    monkeypatch.setattr(switch_mod, "async_send_command", fake_send)

    await sw.async_turn_on()
    assert sent == [CMD_AC_ON]
    assert sw.is_on is True

    # A poll that still says off keeps the guess.
    sw._handle_coordinator_update()
    assert sw.is_on is True

    coordinator.data = [_car(True)]
    sw._handle_coordinator_update()
    assert sw.is_on is True


@pytest.mark.asyncio
async def test_finished_command_drops_the_guess(monkeypatch):
    coordinator, sw = _switch(False)
    monkeypatch.setattr(sw, "async_write_ha_state", lambda: None)
    monkeypatch.setattr(switch_mod, "async_send_command",
                        lambda *a, **k: _noop())

    async def _noop():
        return None

    await sw.async_turn_on()
    assert sw.is_on is True

    event = type("E", (), {"data": {"vin": "VIN1", "command_type": CMD_AC_ON,
                                    "result": "timeout"}})()
    sw._command_finished(event)
    assert sw.is_on is False
