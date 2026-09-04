import pytest
from opencarwings_client import Car, CarSerializerList

from custom_components.ha_opencarwings.util import CarData

DETAIL = {
    "vin": "SJNFAAZE0U1000001",
    "nickname": "MyCar",
    "owner": 1,
    "sms_config": {},
    "tcu_configuration": {},
    "location": {},
    "ev_info": {},
    "send_to_car_location_all": [],
    "route_plans": [],
    "timer_commands": [],
    "command_type_display": "Refresh data",
    "command_result_display": "OK",
}


def _detail(**over) -> CarData:
    car = Car.from_dict({**DETAIL, **over})
    return CarData(vin=car.vin, car_detail=car)


@pytest.mark.parametrize(
    "tcu_ver,expected",
    [
        (None, "LEAF ZE0"),
        ("06.42", "LEAF AZE0"),
        ("TCU032", "LEAF AZE0 (2016-17)"),
        ("TCU033", "LEAF ZE1"),
        # An unknown TCU version is treated as the oldest car.
        ("nonsense", "LEAF ZE0"),
    ],
)
def test_leaf_generation_comes_from_the_tcu_version(tcu_ver, expected):
    assert _detail(tcu_ver=tcu_ver).car_model_data()["model"] == expected


@pytest.mark.parametrize(
    "tcu_ver,expected",
    [(None, "e-NV200"), ("TCU033", "e-NV200 40 kWh"), ("06.42", "e-NV200")],
)
def test_the_van_is_told_apart_by_its_vin(tcu_ver, expected):
    car = _detail(vin="VSKHAME0Z00000001", tcu_ver=tcu_ver)
    assert car.car_model_data()["model"] == expected


def test_device_carries_the_tcu_firmware_and_serial():
    info = _detail(tcu_ver="TCU033", tcu_model="AB-1234", tcu_version="1.2.3").car_model_data()

    assert info["name"] == "MyCar"
    assert info["manufacturer"] == "NISSAN"
    assert info["model"] == "LEAF ZE1"
    assert info["serial_number"] == "AB-1234"
    assert info["sw_version"] == "1.2.3"


def test_a_list_only_car_falls_back_to_the_oldest_model():
    # The list endpoint carries no TCU version, so the generation cannot be told.
    listed = CarSerializerList.from_dict(
        {"vin": "SJNFAAZE0U1000001", "nickname": "MyCar", "ev_info": {}, "location": {}}
    )
    info = CarData(vin=listed.vin, list_car=listed).car_model_data()

    assert info["model"] == "LEAF ZE0"
    assert "serial_number" not in info


def test_a_car_with_nothing_fetched_is_named_after_its_vin():
    info = CarData(vin="VIN1").car_model_data()

    assert info["name"] == "VIN1"
    assert "model" not in info
