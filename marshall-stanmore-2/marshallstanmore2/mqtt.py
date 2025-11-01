import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from aiomqtt import Message, Client, Will
from typing import Coroutine


from marshallstanmore2 import (
    MarshallStanmore2,
    EqProfile,
    Status,
    MediaInfo,
    EqPreset,
    AudioSource,
)
from marshallstanmore2.exceptions import (
    InvalidDeviceName,
    InvalidVolume,
    InvalidLedBrightness,
)

logger = logging.getLogger("stanmore2.mqtt")
SLEEP_TIME_BEFORE_PUBLISHING_BACK = 0.5


def _preset_to_str(preset: EqPreset | None):
    if preset is not None:
        return preset.name.lower()
    else:
        return "custom"


def _profile_to_str(eq_profile: EqProfile):
    return " ".join((str(i) for i in eq_profile))


def _add_task(coro: Coroutine):
    return asyncio.get_running_loop().create_task(coro)


class MqttControl:
    _mqtt_client: Client
    _stack: AsyncExitStack
    _speaker: MarshallStanmore2
    _topic_prefix: str
    _mqtt_retain: bool

    def __init__(
        self,
        *,
        ble_address: str,
        mqtt_hostname: str = "127.0.0.1",
        mqtt_port: int = 1883,
        mqtt_username: str | None = None,
        mqtt_password: str | None = None,
        mqtt_topic_prefix: str = "stanmore2",
        mqtt_retain: bool = False,
        allow_pairing: bool = False,
    ) -> None:
        self._mqtt_retain = mqtt_retain
        self._allow_pairing = allow_pairing
        self._topic_prefix = mqtt_topic_prefix
        self._stack = AsyncExitStack()

        self._mqtt_client = self._create_mqtt_client(
            hostname=mqtt_hostname,
            port=mqtt_port,
            username=mqtt_username,
            password=mqtt_password,
            will=Will(
                topic=self.topic("lwt"),
                payload="offline",
                retain=True,
            ),
        )

        self._speaker = MarshallStanmore2(ble_address)
        self._init_speaker()

    def _create_mqtt_client(self, **kwargs) -> Client:
        return Client(**{k: v for k, v in kwargs.items() if v is not None})

    def _init_speaker(self) -> None:
        self._speaker.register_disconnect_callback(self._ble_disconnect_callback)
        self._speaker.register_equalizer_callback(self._ble_equalizer_callback)
        self._speaker.register_volume_callback(self._ble_volume_callback)
        self._speaker.register_status_callback(self._ble_status_callback)
        self._speaker.register_volume_callback(self._ble_volume_callback)
        self._speaker.register_media_info_callback(self._ble_media_info_callback)

    def _ble_disconnect_callback(self) -> None:
        logger.error("BLE disconnected")
        raise SystemExit(1)

    def _ble_equalizer_callback(self, eq_profile: EqProfile) -> None:
        _add_task(self._publish_eq_profile(eq_profile))
        try:
            eq_preset = EqPreset(eq_profile)
        except ValueError:
            eq_preset = None
        _add_task(self._publish_eq_preset(eq_preset))

    def _ble_status_callback(self, status: Status) -> None:
        _add_task(self._publish_status(status))

    def _ble_volume_callback(self, volume: int):
        self._sync_publish(self.topic("info/volume"), str(volume))

    def _sync_publish(self, topic, payload):
        return _add_task(self._publish(topic, payload))

    async def _publish(self, topic, payload, retain: bool | None = None):
        retain = retain if retain is not None else self._mqtt_retain

        logger.info(
            "publishing to topic: %r, payload %r, retain: %r", topic, payload, retain
        )
        await self._mqtt_client.publish(topic, payload, retain=retain)

    def _ble_media_info_callback(self, media_info: MediaInfo):
        self._sync_publish(self.topic("info/media/title"), media_info.title)
        self._sync_publish(self.topic("info/media/artist"), media_info.artist)
        self._sync_publish(self.topic("info/media/album"), media_info.album)

    def topic(self, topic_name: str) -> str:
        return f"{self._topic_prefix}/{topic_name}"

    async def wakeup(self):
         if not self._speaker.is_connected:
        await self._stack.enter_async_context(self._speaker)
        await self.get_status()

    async def start(self):
        async with self._stack:
            await self._stack.enter_async_context(self._mqtt_client)

            main_topic = self.topic("command/#")
            logger.info("MQTT: Subscribing to: %s ...", main_topic)
            await self._mqtt_client.subscribe(main_topic)

            logger.info("MQTT: Publishing 'online' to %s ...", self.topic("lwt"))
            await self._publish(self.topic("lwt"), "online", retain=True)

            logger.info("MQTT: Starting message handler ...")
            await self._handle_messages()

    async def _handle_messages(self):
        async for message in self._mqtt_client.messages:
            logger.info(
                "Message inbound from topic: %r, payload: %r",
                message.topic,
                message.payload,
            )
            await self._handle_command(message)

    async def get_volume(self):
        volume = await self._speaker.get_volume()
        await self._publish(self.topic("info/volume"), str(volume))

    async def set_volume(self, payload: bytes):
        try:
            volume = int(payload.decode())
            await self._speaker.set_volume(volume)
            await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
            await self.get_volume()
        except (ValueError, InvalidVolume):
            logger.error("Bad set_volume value received")

    async def set_eq_preset(self, name: bytes):
        try:
            name_str = name.decode().upper()
            preset = EqPreset[name_str]
        except (ValueError, KeyError):
            logger.error("Invalid set_eq_preset value received")
            return

        await self._speaker.set_equaliser_preset(preset)
        await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
        await self.get_eq_preset()
        await self.get_eq_profile()

    async def _publish_eq_preset(self, eq_preset: EqPreset | None):
        preset_name = _preset_to_str(eq_preset)
        await self._publish(self.topic("info/eq_preset"), preset_name)

    async def get_eq_preset(self):
        eq_preset = await self._speaker.get_equaliser_preset()
        await self._publish_eq_preset(eq_preset)

    async def set_eq_profile(self, eq_profile_bytes: bytes):
        def error():
            logger.error("Invalid set_eq_profile value received", stacklevel=2)

        try:
            profile_str = (
                eq_profile_bytes.decode()
            )  # may raise UnicodeDecodeError (caught by ValueError)
            profile_str_split = profile_str.split(" ")

            if len(profile_str_split) != 5:
                error()
                return

            eq_integers = (int(i) for i in profile_str_split)  # may raise ValueError
            profile = EqProfile(*eq_integers)  # may raise ValueError

        except ValueError:
            error()
            return

        else:
            await self._speaker.set_equaliser_profile(profile)
            await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
            await self.get_eq_profile()
            await self.get_eq_preset()

    async def _set_individual_eq(self, hz_str: str, value: bytes):
        def error():
            logger.error(f"Invalid set_eq_profile/{hz_str}hz value received")

        eq_profile = await self._speaker.get_equaliser_profile()
        try:
            eq_value = int(value)
        except ValueError:
            error()
            return
        else:
            if not 0 <= eq_value <= 10:
                error()
                return
            setattr(eq_profile, f"hz{hz_str}", eq_value)
            await self._speaker.set_equaliser_profile(eq_profile)
            await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
            await self.get_eq_profile()
            await self.get_eq_preset()

    async def set_eq_profile_individual(self, message: Message):
        if message.topic.matches(self.topic("command/set_eq_profile/160hz")):
            await self._set_individual_eq("160", message.payload)
        elif message.topic.matches(self.topic("command/set_eq_profile/400hz")):
            await self._set_individual_eq("400", message.payload)
        elif message.topic.matches(self.topic("command/set_eq_profile/1000hz")):
            await self._set_individual_eq("1000", message.payload)
        elif message.topic.matches(self.topic("command/set_eq_profile/2500hz")):
            await self._set_individual_eq("2500", message.payload)
        elif message.topic.matches(self.topic("command/set_eq_profile/6250hz")):
            await self._set_individual_eq("6250", message.payload)

    async def _publish_eq_profile(self, eq_profile: EqProfile):
        profile_str = _profile_to_str(eq_profile)
        await self._publish(self.topic("info/eq_profile"), profile_str)
        await self._publish_individual_eq("160", eq_profile.hz160)
        await self._publish_individual_eq("400", eq_profile.hz400)
        await self._publish_individual_eq("1000", eq_profile.hz1000)
        await self._publish_individual_eq("2500", eq_profile.hz2500)
        await self._publish_individual_eq("6250", eq_profile.hz6250)

    async def _publish_individual_eq(self, hz_str: str, value: int):
        await self._publish(self.topic(f"info/eq_profile/{hz_str}hz"), str(value))

    async def get_eq_profile(self) -> None:
        eq_profile = await self._speaker.get_equaliser_profile()
        await self._publish_eq_profile(eq_profile)

    async def get_device_name(self) -> None:
        name = await self._speaker.get_device_name()
        await self._publish(self.topic("info/device_name"), name)

    async def set_device_name(self, name_bytes: bytes) -> None:
        def error():
            logger.error("Invalid device name received", stacklevel=2)

        try:
            name_str = name_bytes.decode()
        except ValueError:
            error()
            return

        try:
            await self._speaker.set_device_name(name_str)
        except InvalidDeviceName:
            error()
            return
        await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
        await self.get_device_name()

    async def set_led_brightness(self, brightness_bytes: bytes):
        try:
            brightness_int = int(brightness_bytes)
            await self._speaker.set_led_brightness(brightness_int)
        except (ValueError, InvalidLedBrightness):
            logger.error("Invalid set_led_brightness value received")
        else:
            await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
            await self.get_led_brightness()

    async def get_led_brightness(self):
        brightness = await self._speaker.get_led_brightness()
        await self._publish(self.topic("info/led_brightness"), str(brightness))

    async def _publish_status(self, status: Status):
        await self._publish(
            self.topic("info/play_status"), status.play_status.name.lower()
        )
        await self._publish(
            self.topic("info/audio_source"), status.audio_source.name.lower()
        )
        await self._publish(
            self.topic("info/interaction_sound_enabled"),
            str(int(status.interaction_sound_enabled)),
        )

    async def get_status(self):
        status = await self._speaker.get_status()
        await self._publish_status(status)

    async def play(self):
        await self._speaker.play()

    async def pause(self):
        await self._speaker.pause()

    async def next(self):
        await self._speaker.next()

    async def previous(self):
        await self._speaker.previous()

    async def set_interaction_sound(self, enabled_bytes: bytes):
        try:
            enabled_bytes_str = enabled_bytes.decode()
            enabled_bool = bool(int(enabled_bytes_str))
        except ValueError:
            logger.error("Invalid set_interaction_sound value received")
        else:
            await self._speaker.set_interaction_sound(enabled_bool)
            await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
            await self.get_status()

    async def set_source(self, source_bytes: bytes):
        try:
            source_str = source_bytes.decode().upper()
            source = AudioSource[source_str]
        except (ValueError, KeyError):
            logger.error("Invalid set_source value received")
        else:
            await self._speaker.set_source(source)
            await asyncio.sleep(SLEEP_TIME_BEFORE_PUBLISHING_BACK)
            await self.get_status()

    async def enter_pairing_mode(self):
        await self._speaker.enter_pairing_mode()

    async def _handle_command(self, message: Message):
        if message.topic.matches(self.topic("command/set_volume")):
            await self.set_volume(message.payload)

        elif message.topic.matches(self.topic("command/get_volume")):
            await self.get_volume()

        elif message.topic.matches(self.topic("command/set_eq_preset")):
            await self.set_eq_preset(message.payload)

        elif message.topic.matches(self.topic("command/get_eq_preset")):
            await self.get_eq_preset()

        elif message.topic.matches(self.topic("command/set_eq_profile")):
            await self.set_eq_profile(message.payload)

        elif message.topic.matches(self.topic("command/set_eq_profile/+")):
            await self.set_eq_profile_individual(message)

        elif message.topic.matches(self.topic("command/get_eq_profile")):
            await self.get_eq_profile()

        elif message.topic.matches(self.topic("command/set_device_name")):
            await self.set_device_name(message.payload)

        elif message.topic.matches(self.topic("command/get_device_name")):
            await self.get_device_name()

        elif message.topic.matches(self.topic("command/set_led_brightness")):
            await self.set_led_brightness(message.payload)

        elif message.topic.matches(self.topic("command/get_led_brightness")):
            await self.get_led_brightness()

        elif message.topic.matches(self.topic("command/play")):
            await self.play()

        elif message.topic.matches(self.topic("command/pause")):
            await self.pause()

        elif message.topic.matches(self.topic("command/next")):
            await self.next()

        elif message.topic.matches(self.topic("command/previous")):
            await self.previous()

        elif message.topic.matches(self.topic("command/set_interaction_sound")):
            await self.set_interaction_sound(message.payload)

        elif message.topic.matches(self.topic("command/get_status")):
            await self.get_status()

        elif message.topic.matches(self.topic("command/set_source")):
            await self.set_source(message.payload)

        elif message.topic.matches(self.topic("command/wakeup")):
            await self.wakeup()

        elif self._allow_pairing and message.topic.matches(
            self.topic("command/enter_pairing_mode")
        ):
            await self.enter_pairing_mode()


async def main():
    control = MqttControl(ble_address=sys.argv[1], allow_pairing=True)
    await control.start()


if __name__ == "__main__":
    logger.setLevel("INFO")
    logging.basicConfig()
    asyncio.run(main())
