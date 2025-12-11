import logging
import sys
from io import BytesIO
from typing import OrderedDict, Callable, ClassVar

from bleak import BleakClient, BleakGATTCharacteristic

from marshallstanmore2.exceptions import (
    InvalidVolume,
    InvalidDeviceName,
    InvalidCallbackID,
    InvalidLedBrightness,
)
from marshallstanmore2.typings import (
    VolumeCallback,
    MediaInfoCallback,
    AudioSource,
    INT_AUD_SRC_MAPPING,
    StatusIndex,
    INT_PLAY_STATUS_MAPPING,
    AUD_SRC_CMD_MAPPING,
    CMD_MAPPING,
    EqProfile,
    EqPreset,
    StatusCallback,
    DisconnectCallback,
    Status,
    MediaInfo,
    EqualizerCallback,
)

logger = logging.getLogger("stanmore2.ble")


class MarshallStanmore2:
    """Bluetooth interface for controlling Marshall Stanmore II speaker.

    Provides methods to connect, control playback, adjust volume, manage equalizer and LED, and handle BLE events.
    """

    volume_characteristic: ClassVar[str] = "44fa-50b2-d0a3-472e-a939-d80c-f176-38bb"
    control_characteristic: ClassVar[str] = "4446-cf5f-12f2-4c1e-afe1-b157-9753-5ba8"
    led_brightness_characteristic: ClassVar[str] = (
        "35e3-b090-1d43-35ae-af35-d254-b153-fc36"
    )
    device_name_characteristic: ClassVar[str] = (
        "3ba9-1c2e-8b08-4c27-9d4e-4936-a793-fcfb"
    )
    eq_characteristic: ClassVar[str] = "31fb-b033-1013-bd3e-a249-d856-f156-a319"
    pairing_characteristic: ClassVar[str] = "4a75-c20f-13bd-44a1-b39d-a70f-86f6-07a2"
    media_info_characteristic: ClassVar[str] = "95c0-9f26-95a4-4597-a798-b8e4-08f5-ca66"

    _media_info_ending_bytes: bytes = bytes(
        [0x00, 0x00, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00]
    )
    client: BleakClient
    _address: str

    _volume_change_callbacks: OrderedDict[int, VolumeCallback]
    _media_info_callbacks: OrderedDict[int, MediaInfoCallback]
    _disconnect_callbacks: OrderedDict[int, DisconnectCallback]
    _status_callbacks: OrderedDict[int, StatusCallback]
    _equalizer_callbacks: OrderedDict[int, EqualizerCallback]
    _media_info_buffer: BytesIO

    def __init__(self, address: str):
        """Initialize with the BLE address of the speaker.

        Args:
            address (str): BLE address of the speaker.
        """
        self._address = address

        self._volume_change_callbacks = OrderedDict()
        self._media_info_callbacks = OrderedDict()
        self._disconnect_callbacks = OrderedDict()
        self._status_callbacks = OrderedDict()
        self._equalizer_callbacks = OrderedDict()

        self._media_info_buffer = BytesIO()

    @property
    def is_connected(self) -> bool:
        return self.client.is_connected

    async def __aenter__(self):
        logger.info("Connecting ...")
        self.client = await BleakClient(
            self._address,
            timeout=60,
            disconnected_callback=self._on_disconnect,
        ).__aenter__()
        logger.info("Connected")
        try:
            logger.info("Registering status callback ...")
            await self.client.start_notify(
                self.control_characteristic,
                self._on_status_change,
            )
            logger.info("Status callback registered")

            logger.info("Registering volume callback ...")
            await self.client.start_notify(
                self.volume_characteristic, self._on_volume_change
            )
            logger.info("Volume callback registered")

            logger.info("Registering media info callback ...")
            await self.client.start_notify(
                self.media_info_characteristic, self._on_media_info
            )
            logger.info("Media info callback registered")

            logger.info("Registering equalizer callback ...")
            await self.client.start_notify(
                self.eq_characteristic, self._on_equalizer_change
            )
            logger.info("Equalizer callback registered")

        except:  # noqa
            await self.client.__aexit__(*sys.exc_info())

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    def _on_volume_change(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        logger.info("Volume notification data: %d", data[0])
        for callback in self._volume_change_callbacks.values():
            callback(data[0])

    @staticmethod
    def _decode_status(data):
        return Status(
            audio_source=INT_AUD_SRC_MAPPING[data[StatusIndex.SOURCE]],
            play_status=INT_PLAY_STATUS_MAPPING[data[StatusIndex.PLAY_STATUS]],
            interaction_sound_enabled=data[StatusIndex.INTERATION_SOUND] == 1,
        )

    def _on_status_change(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        logger.info("Status notification data %r", data.hex(sep="-", bytes_per_sep=1))
        status = self._decode_status(data)
        logger.info("Current status: %r", status)

        for callback in self._status_callbacks.values():
            callback(status)

    def _on_disconnect(self, _: BleakClient) -> None:
        logger.info("Disconnected")
        for callback in self._disconnect_callbacks.values():
            callback()

    @staticmethod
    def _decode_index(data: bytes, offset: int) -> str:
        data_length_pos = offset + 7
        data_start_pos = data_length_pos + 1
        data_length = data[data_length_pos]
        return data[data_start_pos : data_start_pos + data_length].decode()

    def _handle_media_info(self):
        ### 00 00 00 index 00 6a 00 length
        ## index: 01: title 02 artist 03 album
        ## if sees 00 00 00 ff 00 00 00 00 means packet done
        data = self._media_info_buffer.getvalue()
        try:
            title_start_pos = data.index(
                bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x6A, 0x00])
            )
            if title_start_pos == -1:
                title = None
            else:
                title = self._decode_index(data, title_start_pos)

            artist_start_pos = data.index(
                bytes([0x00, 0x00, 0x00, 0x02, 0x00, 0x6A, 0x00])
            )
            if artist_start_pos == -1:
                artist = None
            else:
                artist = self._decode_index(data, artist_start_pos)

            album_start_pos = data.index(
                bytes([0x00, 0x00, 0x00, 0x03, 0x00, 0x6A, 0x00])
            )
            if album_start_pos == -1:
                album = None
            else:
                album = self._decode_index(data, album_start_pos)

            media_info = MediaInfo(title, artist, album)
            logger.info("Media info: %r, %r, %r", media_info)

            for callback in self._media_info_callbacks.values():
                callback(media_info)
        finally:
            self._media_info_buffer = BytesIO()

    def _on_media_info(self, _: BleakGATTCharacteristic, data: bytearray):
        logger.info(
            "Media info notification data: %s", data.hex(sep="-", bytes_per_sep=1)
        )
        self._media_info_buffer.write(data)
        if data[-8:] == self._media_info_ending_bytes:
            self._handle_media_info()

    def _on_equalizer_change(self, _: BleakGATTCharacteristic, data: bytearray):
        logger.info(
            "Equalizer notification data: %s", data.hex(sep="-", bytes_per_sep=1)
        )
        eq = EqProfile(*data)
        for callback in self._equalizer_callbacks.values():
            callback(eq)

    async def get_status(self) -> Status:
        """Get current speaker status.

        Returns:
            Status: Object containing current speaker status.
        """
        data = await self.client.read_gatt_char(
            self.control_characteristic,
        )
        logger.info("Status changed %r", data.hex(sep=" ", bytes_per_sep=1))
        status = self._decode_status(data)
        logger.info("Current status: %r", status)
        return status

    async def set_volume(self, volume: int) -> None:
        """Set speaker volume.

        Args:
            volume (int): Volume level (0-32).

        Raises:
            InvalidVolume: If volume is out of range.
        """
        if not (0 <= volume <= 32):
            raise InvalidVolume("Volume must be within 0 and 32")

        await self.client.write_gatt_char(
            self.volume_characteristic, bytearray([volume]), response=True
        )

    async def get_volume(self) -> int:
        """Get current speaker volume.

        Returns:
            int: Current volume level (0-32).
        """
        return (await self.client.read_gatt_char(self.volume_characteristic))[0]

    async def _send_command(self, cmd_int: int) -> None:
        """Send a command to the speaker.

        Args:
            cmd_int (int): Command integer.
        """
        buffer = bytearray([cmd_int])
        await self.client.write_gatt_char(
            self.control_characteristic, buffer, response=True
        )

    async def set_source(self, source: AudioSource) -> None:
        """Select audio input source.

        Args:
            source (AudioSource): AudioSource to activate.
        """
        cmd_int = AUD_SRC_CMD_MAPPING[source]
        logger.info("Setting audio source %s", source)
        await self._send_command(cmd_int)

    async def next(self) -> None:
        """Skip to next track in playlist."""
        cmd_int = CMD_MAPPING["next"]
        logger.info("Sending command: next")
        await self._send_command(cmd_int)

    async def previous(self) -> None:
        """Return to previous track in playlist."""
        cmd_int = CMD_MAPPING["previous"]
        logger.info("Sending command: previous")
        await self._send_command(cmd_int)

    async def play(self) -> None:
        """Start audio playback."""
        cmd_int = CMD_MAPPING["play"]
        logger.info("Sending command: play")
        await self._send_command(cmd_int)

    async def pause(self) -> None:
        """Pause audio playback."""
        cmd_int = CMD_MAPPING["pause"]
        logger.info("Sending command: pause")
        await self._send_command(cmd_int)

    async def set_interaction_sound(self, enabled: bool) -> None:
        """Toggle button feedback sounds.

        Args:
            enabled (bool): True to enable interaction sounds.
        """
        action = "enable_interation_sound" if enabled else "disable_interation_sound"
        cmd_int = CMD_MAPPING[action]
        logger.info("Sending command: %s", action)
        await self._send_command(cmd_int)

    async def set_led_brightness(self, brightness: int) -> None:
        """Set LED brightness.

        Args:
            brightness (int): LED brightness [0, 35].

        Raises:
            InvalidLedBrightness: If brightness is out of range.
        """
        if not (0 <= brightness <= 35):
            raise InvalidLedBrightness("LED brightness must be between 0 and 35")

        actual_brightness = brightness + 35
        await self.client.write_gatt_char(
            self.led_brightness_characteristic,
            bytearray([actual_brightness]),
            response=True,
        )

    async def get_led_brightness(self) -> int:
        """Get current LED brightness.

        Returns:
            int: Current LED brightness (0-35).
        """
        data = await self.client.read_gatt_char(self.led_brightness_characteristic)
        return data[0] - 35

    def _register_callback(self, attr: str, callback: Callable) -> int:
        callback_dict: OrderedDict[int, Callable] = getattr(self, attr)
        try:
            callback_id = next(reversed(callback_dict)) + 1
        except StopIteration:
            callback_id = 1
        callback_dict[callback_id] = callback
        return callback_id

    def _cancel_callback(self, attr: str, callback_id: int) -> None:
        callback_dict: OrderedDict[int, Callable] = getattr(self, attr)
        try:
            del callback_dict[callback_id]
        except KeyError:
            raise InvalidCallbackID("Invalid callback ID")

    def register_disconnect_callback(self, callback: DisconnectCallback) -> int:
        """Register disconnect event handler.

        Args:
            callback (DisconnectCallback): Function to call on disconnect.

        Returns:
            int: Callback ID for cancellation.
        """
        return self._register_callback("_disconnect_callbacks", callback)

    def cancel_disconnect_callback(self, callback_id: int) -> None:
        """Remove disconnect callback.

        Args:
            callback_id (int): ID returned from registration.
        """
        return self._cancel_callback("_disconnect_callbacks", callback_id)

    def register_status_callback(self, callback: StatusCallback) -> int:
        """Register status update handler.

        Args:
            callback (StatusCallback): Function receiving status updates.

        Returns:
            int: Callback ID for cancellation.
        """
        return self._register_callback("_status_callbacks", callback)

    def cancel_status_callback(self, callback_id: int) -> None:
        """Remove status update callback.

        Args:
            callback_id (int): ID returned from registration.
        """
        return self._cancel_callback("_status_callbacks", callback_id)

    def register_volume_callback(self, callback: VolumeCallback) -> int:
        """Register volume change handler.

        Args:
            callback (VolumeCallback): Function receiving volume updates.

        Returns:
            int: Callback ID for cancellation.
        """
        return self._register_callback("_volume_change_callbacks", callback)

    def cancel_volume_callback(self, callback_id: int) -> None:
        """Remove volume change callback.

        Args:
            callback_id (int): ID returned from registration.
        """
        return self._cancel_callback("_volume_change_callbacks", callback_id)

    def register_equalizer_callback(self, callback: EqualizerCallback) -> int:
        """Register equalizer change handler.

        Args:
            callback (EqualizerCallback): Function receiving EQ updates.

        Returns:
            int: Callback ID for cancellation.
        """
        return self._register_callback("_equalizer_callbacks", callback)

    def cancel_equalizer_callback(self, callback_id: int) -> None:
        """Remove equalizer change callback.

        Args:
            callback_id (int): ID returned from registration.
        """
        return self._cancel_callback("_equalizer_callbacks", callback_id)

    def register_media_info_callback(self, callback: MediaInfoCallback) -> int:
        """Register media metadata handler.

        Args:
            callback (MediaInfoCallback): Function receiving track info.

        Returns:
            int: Callback ID for cancellation.
        """
        return self._register_callback("_media_info_callbacks", callback)

    def cancel_media_info_callback(self, callback_id: int) -> None:
        """Remove media info callback.

        Args:
            callback_id (int): ID returned from registration.
        """
        return self._cancel_callback("_media_info_callbacks", callback_id)

    async def set_device_name(self, name: str) -> None:
        """Set device name.

        Args:
            name (str): New device name.

        Raises:
            InvalidDeviceName: If name is too long.
        """
        encoded = name.encode("utf-8")

        if not (0 < len(encoded) <= 17):
            raise InvalidDeviceName(
                "Device name length must be between 0 and 17 bytes after encoding"
            )

        data = bytearray([0x01, len(encoded), *encoded])
        logger.info("Sending device name data: %s", data.hex(sep=" ", bytes_per_sep=1))
        await self.client.write_gatt_char(
            self.device_name_characteristic, data, response=True
        )

    async def get_device_name(self) -> str:
        """Get current device name.

        Returns:
            str: Current device name.
        """
        data = await self.client.read_gatt_char(self.device_name_characteristic)
        logger.info("Device name data: %s", data.hex(sep=" ", bytes_per_sep=1))
        return data[2:].decode()

    async def set_equaliser_profile(self, profile: EqProfile) -> None:
        """Set equalizer profile.

        Args:
            profile (EqProfile): EqProfile to set.
        """
        data = bytearray(profile)
        logger.info(
            "Setting equalizer with data: %s", data.hex(sep=" ", bytes_per_sep=1)
        )
        await self.client.write_gatt_char(self.eq_characteristic, data, response=True)

    async def get_equaliser_profile(self) -> EqProfile:
        """Get current equalizer profile.

        Returns:
            EqProfile: Current EqProfile.
        """
        data = await self.client.read_gatt_char(self.eq_characteristic)
        logger.info("Equalizer data: %s", data.hex(sep="-", bytes_per_sep=1))
        return EqProfile(*data)

    async def set_equaliser_preset(self, preset: EqPreset) -> None:
        """Set equalizer preset.

        Args:
            preset (EqPreset): EqPreset to set.
        """
        await self.set_equaliser_profile(preset.value)

    async def get_equaliser_preset(self) -> EqPreset | None:
        """Get current equalizer preset.

        Returns:
            EqPreset | None: EqPreset if current profile matches a preset,
            otherwise None.
        """
        profile = await self.get_equaliser_profile()
        try:
            return EqPreset(profile)
        except ValueError:
            return None

    async def enter_pairing_mode(self) -> None:
        """Enable Bluetooth pairing mode.

        Note: This will disconnect BLE after execution
        """
        await self.client.write_gatt_char(
            self.pairing_characteristic, bytearray([0]), response=True
        )
