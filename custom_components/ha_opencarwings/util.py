from typing import Optional, Union

from opencarwings_client import Car, CarSerializerList, VehicleHealthInfo

from . import DOMAIN


def _relax_dtc_fields() -> None:
    """The server sends dtc_short and dtc_long as lists, the model wants dicts.

    Without this any car with a health report fails to parse. Reported upstream.
    """
    for name in ("dtc_short", "dtc_long"):
        field = VehicleHealthInfo.model_fields.get(name)
        if field is not None:
            field.annotation = Optional[Union[dict, list]]
    # Car embeds it, so rebuild that too.
    for model in (VehicleHealthInfo, Car, CarSerializerList):
        model.model_rebuild(force=True)


_relax_dtc_fields()

# The TCU version tells the generations apart; the VIN prefix picks car or van.
TCU_GENERATIONS = {
    "06.42": "LEAF AZE0",
    "TCU032": "LEAF AZE0 (2016-17)",
    "TCU033": "LEAF ZE1",
}
ENV200_GENERATIONS = {"TCU033": "e-NV200 40 kWh"}


class CarData:
    vin: str
    list_car: CarSerializerList|None = None
    car_detail: Car|None = None

    def __init__(self, vin: str, list_car: CarSerializerList|None = None, car_detail: Car|None = None):
        self.vin = vin
        self.list_car = list_car
        self.car_detail = car_detail

    def as_dict(self) -> dict:
        """The car as a plain dict.

        to_dict drops read-only fields, supported_commands among them.
        """
        car = self.get_latest_car()
        if car is None:
            return {}
        return car.model_dump(by_alias=True, exclude_none=True)

    def get_latest_car(self) -> Car|CarSerializerList|None:
        if self.car_detail:
            return self.car_detail
        return self.list_car

    def apply_push(self, obj_type: str, data: dict) -> bool:
        """Merge a websocket push. False means nothing changed."""
        car = self.car_detail or self.list_car
        if car is None:
            return False

        # to_dict drops read-only fields (ids, supported_commands), and losing
        # the nested ids breaks matching for every later push.
        flat = car.model_dump(by_alias=True, exclude_none=True)
        if obj_type == "car":
            flat.update(data)
        else:
            flat[obj_type] = {**(flat.get(obj_type) or {}), **data}

        try:
            rebuilt = type(car).from_dict(flat)
        except Exception:
            return False
        if rebuilt is None:
            return False

        if self.car_detail:
            self.car_detail = rebuilt
        else:
            self.list_car = rebuilt
        return True

    @classmethod
    def from_push(cls, vin: str, data: dict) -> "CarData|None":
        """Build a car we have not seen before from a push."""
        try:
            return cls(vin=vin, car_detail=Car.from_dict(data))
        except Exception:
            return None

    def car_model_data(self) -> dict:
        car_instance = self.get_latest_car()

        if car_instance is not None:
            base_obj = {
                "identifiers": {(DOMAIN, self.vin)},
                "name": car_instance.nickname or self.vin,
                "manufacturer": "NISSAN",
            }

            car_generation = "LEAF ZE0"
            if not car_instance.vin.startswith("VSK"):
                if isinstance(car_instance, Car):
                    car_generation = TCU_GENERATIONS.get(car_instance.tcu_ver, car_generation)
            else:
                car_generation = "e-NV200"
                if isinstance(car_instance, Car):
                    car_generation = ENV200_GENERATIONS.get(car_instance.tcu_ver, car_generation)

            base_obj["model"] = car_generation

            if isinstance(car_instance, Car):
                base_obj["serial_number"] = car_instance.tcu_model
                base_obj["sw_version"] = car_instance.tcu_version

            return base_obj
        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": self.vin
        }
