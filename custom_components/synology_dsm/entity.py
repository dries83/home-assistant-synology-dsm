"""Entities for Synology DSM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .common import SynoApi
from .const import ATTRIBUTION, DOMAIN
from .coordinator import (
    SynologyDSMCentralUpdateCoordinator,
    SynologyDSMUpdateCoordinator,
)


@dataclass(frozen=True, kw_only=True)
class SynologyDSMEntityDescription(EntityDescription):
    """Generic Synology DSM entity description."""

    api_key: str


class SynologyDSMBaseEntity[_CoordinatorT: SynologyDSMUpdateCoordinator[Any]](
    CoordinatorEntity[_CoordinatorT]
):
    """Representation of a Synology NAS entry."""

    entity_description: SynologyDSMEntityDescription
    unique_id: str
    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        api: SynoApi,
        coordinator: _CoordinatorT,
        description: SynologyDSMEntityDescription,
    ) -> None:
        """Initialize the Synology DSM entity."""
        super().__init__(coordinator)
        self.entity_description = description

        self._api = api
        information = api.information
        network = api.network
        assert information is not None
        assert network is not None

        self._attr_unique_id: str = (
            f"{information.serial}_{description.api_key}:{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, information.serial)},
            name=network.hostname,
            manufacturer="Synology",
            model=information.model,
            sw_version=information.version_string,
            configuration_url=api.config_url,
        )

    async def async_added_to_hass(self) -> None:
        """Register entity for updates from API."""
        self.async_on_remove(
            self._api.subscribe(self.entity_description.api_key, self.unique_id)
        )
        await super().async_added_to_hass()


class SynologyDSMDeviceEntity(
    SynologyDSMBaseEntity[SynologyDSMCentralUpdateCoordinator]
):
    """Representation of a Synology NAS disk or volume entry."""

    def __init__(
        self,
        api: SynoApi,
        coordinator: SynologyDSMCentralUpdateCoordinator,
        description: SynologyDSMEntityDescription,
        device_id: str | None = None,
    ) -> None:
        """Initialize the Synology DSM disk or volume entity."""
        super().__init__(api, coordinator, description)
        self._device_id = device_id
        self._device_name: str | None = None
        self._device_manufacturer: str | None = None
        self._device_model: str | None = None
        self._device_firmware: str | None = None
        self._device_type = None
        storage = api.storage
        information = api.information
        network = api.network
        external_usb = api.external_usb
        assert information is not None
        assert storage is not None
        assert network is not None

        if "volume" in description.key:
            assert self._device_id is not None
            volume = storage.get_volume(self._device_id)
            assert volume is not None
            # Volume does not have a name
            self._device_name = volume["id"].replace("_", " ").capitalize()
            self._device_manufacturer = "Synology"
            self._device_model = information.model
            self._device_firmware = information.version_string
            self._device_type = (
                volume["device_type"]
                .replace("_", " ")
                .replace("raid", "RAID")
                .replace("shr", "SHR")
            )
        elif "disk" in description.key:
            assert self._device_id is not None
            disk = storage.get_disk(self._device_id)
            assert disk is not None
            self._device_name = disk["name"]
            self._device_manufacturer = disk["vendor"]
            self._device_model = disk["model"].strip()
            self._device_firmware = disk["firm"]
            self._device_type = disk["diskType"]
        elif "device" in description.key:
            assert self._device_id is not None
            assert external_usb is not None
            for device in external_usb.get_devices.values():
                if device.device_name == self._device_id:
                    self._device_name = device.device_name
                    self._device_manufacturer = device.device_manufacturer
                    self._device_model = device.device_product_name
                    self._device_type = device.device_type
                    break
        elif "partition" in description.key:
            assert self._device_id is not None
            assert external_usb is not None
            for device in external_usb.get_devices.values():
                for partition in device.device_partitions.values():
                    if partition.partition_title == self._device_id:
                        self._device_name = partition.partition_title
                        self._device_manufacturer = "Synology"
                        self._device_model = partition.filesystem
                        break

        self._attr_unique_id += f"_{self._device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{information.serial}_{self._device_id}")},
            name=f"{network.hostname} ({self._device_name})",
            manufacturer=self._device_manufacturer,
            model=self._device_model,
            sw_version=self._device_firmware,
            via_device=(DOMAIN, information.serial),
            configuration_url=self._api.config_url,
        )


class SynologyDSMBackupTaskEntity(SynologyDSMBaseEntity):
    """Representation of a Synology Hyper backup task entry."""

    def __init__(
        self,
        api: SynoApi,
        coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]],
        description: SynologyDSMEntityDescription,
        device_id: int | None = None,
    ) -> None:
        """Initialize the Synology DSM disk or volume entity."""
        super().__init__(api, coordinator, description)
        self._device_id = device_id
        self._device_name: str | None = None
        self._device_manufacturer: str | None = None
        self._device_model: str | None = None
        self._device_type = None

        task = self._api.hyper_backup.get_task(self._device_id)
        self._device_manufacturer = "Synology"
        self._device_name = task['name']
        if task['transfer_type'].startswith('image_'):  # rename "image_local" to "Local Image", etc
            task['transfer_type'] = task['transfer_type'][6:] + ' image'
        self._device_model = task['transfer_type'].replace("_", " ").title() + ' Backup Task'

        self._attr_name = (
            f"{self._device_name} {description.name}"
        )
        self._attr_unique_id += f"_hyper_{self._device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._api.information.serial}_hyper_{self._device_id}")},
            name=f"{self._device_name}",
            manufacturer=self._device_manufacturer,
            model=self._device_model,
            via_device=(DOMAIN, self._api.information.serial),
            configuration_url=self._api.config_url,
        )
