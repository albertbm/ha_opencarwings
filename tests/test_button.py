import pytest

from conftest import make_car, stub_commands

from custom_components.ha_opencarwings import button as button_mod


@pytest.mark.asyncio
async def test_refresh_button_created_and_has_unique_id():
    coord = type("C", (), {"data": None})()
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": coord}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await button_mod.async_setup_entry(hass, entry, add)

    assert len(added) == 1
    btn = added[0]
    assert btn.unique_id == "ha_opencarwings_refresh_e1"


@pytest.mark.asyncio
async def test_refresh_button_triggers_coordinator_refresh(monkeypatch):
    class FakeCoordinator:
        def __init__(self):
            self.called = False

        async def async_request_refresh(self):
            self.called = True

    coord = FakeCoordinator()
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": coord}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await button_mod.async_setup_entry(hass, entry, add)

    btn = added[0]
    await btn.async_press()

    assert coord.called is True


@pytest.mark.asyncio
async def test_car_refresh_button_created_and_has_unique_id():
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": None, "cars": [make_car(vin="VIN1", nickname="M1")]}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await button_mod.async_setup_entry(hass, entry, add)

    # Three fixed buttons, plus one per supported command.
    assert len(added) == 3 + len(button_mod.COMMAND_BUTTONS)

    # find the car button
    car_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_refresh_"):
            car_btn = ent
            break

    assert car_btn is not None
    assert car_btn.unique_id == "ha_opencarwings_car_refresh_VIN1"


@pytest.mark.asyncio
async def test_car_refresh_button_is_named_by_translation():
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": None, "cars": [make_car(vin="VIN1", nickname="MyCar")]}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await button_mod.async_setup_entry(hass, entry, add)

    # find car button
    car_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_refresh_"):
            car_btn = ent
            break

    assert car_btn is not None
    assert car_btn._attr_translation_key == "refresh"


@pytest.mark.asyncio
async def test_car_refresh_button_is_attached_to_the_car_device():
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": None, "cars": [make_car(vin="VIN1", nickname="MyCar")]}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await button_mod.async_setup_entry(hass, entry, add)

    # find car button
    car_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_refresh_"):
            car_btn = ent
            break

    assert car_btn is not None
    assert car_btn.device_info["name"] == "MyCar"
    assert list(car_btn.device_info["identifiers"])[0][1] == "VIN1"


@pytest.mark.asyncio
async def test_car_refresh_button_calls_api(monkeypatch):
    calls = stub_commands(monkeypatch)

    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"client": object(), "cars": [make_car(vin="VIN1", nickname="M1")]}}}})()

    from custom_components.ha_opencarwings import button as button_mod
    entry = type("E", (), {"entry_id": "e1"})()

    added = []
    def add(entities):
        added.extend(entities)

    await button_mod.async_setup_entry(hass, entry, add)

    # find car button
    car_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_refresh_"):
            car_btn = ent
            break

    assert car_btn is not None

    await car_btn.async_press()

    vin, request = calls[0]
    assert vin == "VIN1"
    assert request.command_type == 1


@pytest.mark.asyncio
async def test_car_refresh_button_triggers_coordinator_refresh(monkeypatch):
    class FakeCoordinator:
        def __init__(self):
            self.called = False

        async def async_request_refresh(self):
            self.called = True

    calls = stub_commands(monkeypatch)

    coord = FakeCoordinator()
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"client": object(), "coordinator": coord, "cars": [make_car(vin="VIN1", nickname="M1")]}}}})()

    from custom_components.ha_opencarwings import button as button_mod
    entry = type("E", (), {"entry_id": "e1"})()

    added = []
    def add(entities):
        added.extend(entities)

    await button_mod.async_setup_entry(hass, entry, add)

    # find car button
    car_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_refresh_"):
            car_btn = ent
            break

    assert car_btn is not None

    await car_btn.async_press()

    vin, request = calls[0]
    assert vin == "VIN1"
    assert request.command_type == 1
    assert coord.called is True


@pytest.mark.asyncio
async def test_car_chargestart_button_created_and_has_unique_id():
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": None, "cars": [make_car(vin="VIN1", nickname="M1")]}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await button_mod.async_setup_entry(hass, entry, add)

    # find charge start button
    charge_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_chargestart_"):
            charge_btn = ent
            break

    assert charge_btn is not None
    assert charge_btn.unique_id == "ha_opencarwings_car_chargestart_VIN1"


@pytest.mark.asyncio
async def test_car_chargestart_button_is_named_by_translation():
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"coordinator": None, "cars": [make_car(vin="VIN1", nickname="MyCar")]}}}})()

    added = []

    def add(entities):
        added.extend(entities)

    entry = type("E", (), {"entry_id": "e1"})()
    await button_mod.async_setup_entry(hass, entry, add)

    charge_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_chargestart_"):
            charge_btn = ent
            break

    assert charge_btn is not None
    assert charge_btn._attr_translation_key == "charge_start"


@pytest.mark.asyncio
async def test_car_chargestart_button_calls_api(monkeypatch):
    calls = stub_commands(monkeypatch)

    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"client": object(), "cars": [make_car(vin="VIN1", nickname="M1")]}}}})()

    from custom_components.ha_opencarwings import button as button_mod
    entry = type("E", (), {"entry_id": "e1"})()

    added = []
    def add(entities):
        added.extend(entities)

    await button_mod.async_setup_entry(hass, entry, add)

    # find charge start button
    charge_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_chargestart_"):
            charge_btn = ent
            break

    assert charge_btn is not None

    await charge_btn.async_press()

    vin, request = calls[0]
    assert vin == "VIN1"
    assert request.command_type == 2


@pytest.mark.asyncio
async def test_car_chargestart_button_triggers_coordinator_refresh(monkeypatch):
    class FakeCoordinator:
        def __init__(self):
            self.called = False

        async def async_request_refresh(self):
            self.called = True

    calls = stub_commands(monkeypatch)

    coord = FakeCoordinator()
    hass = type("H", (), {"data": {"ha_opencarwings": {"e1": {"client": object(), "coordinator": coord, "cars": [make_car(vin="VIN1", nickname="M1")]}}}})()

    from custom_components.ha_opencarwings import button as button_mod
    entry = type("E", (), {"entry_id": "e1"})()

    added = []
    def add(entities):
        added.extend(entities)

    await button_mod.async_setup_entry(hass, entry, add)

    # find charge start button
    charge_btn = None
    for ent in added:
        if getattr(ent, "unique_id", "").startswith("ha_opencarwings_car_chargestart_"):
            charge_btn = ent
            break

    assert charge_btn is not None

    await charge_btn.async_press()

    vin, request = calls[0]
    assert vin == "VIN1"
    assert request.command_type == 2
    assert coord.called is True