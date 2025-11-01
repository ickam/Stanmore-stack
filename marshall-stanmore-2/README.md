## Directly Integrate with BLE:

See `marshallstanmore2.ble.MarshallStanmore2`, which can be used to directly control the speaker.

Example:

```python
from marshallstanmore2.ble import MarshallStanmore2, AudioSource

async def main():
    async with MarshallStanmore2("YOUR_SPEAKER_BLUETOOTH_ADDRESS") as speaker:
        print(await speaker.get_status())
        await speaker.set_source(AudioSource.BLUETOOTH)
        await speaker.play()
        await speaker.next()
        await speaker.pause()
        await speaker.set_led_brightness(35)
        print(f"Brightness: {await speaker.get_led_brightness()}")
```

For full usage, see documentation.

## MQTT Communication

This program can be controlled and monitored via MQTT. It acts as both an MQTT subscriber (for commands) and publisher (for info/status).

### MQTT Setup

The following environment variables can be used to configure the MQTT connection:
```
BLE_ADDRESS  # this must be set, it's the BLE address of the speaker
MQTT_HOSTNAME  # default to 127.0.0.1
MQTT_PORT  # default to 1883
MQTT_USERNAME
MQTT_PASSWORD
MQTT_TOPIC_PREFIX  # default is "stanmore2"
MQTT_RETAIN  # whether to set the retain flag on the MQTT messages, default is 0 (false), you should use 1(true) or 0(false) here.
ALLOW_PAIRING  # wheter to allow using MQTT command to enter pairing mode, when this happens the BLE connection will be dropped, and the application will exit.
```
### Command Topics

Publish commands to `<prefix>/command/<action>`. Payloads are typically UTF-8 encoded strings or integers.
All the get_* commands will publish the current value to `<prefix>/info/<name>`, see the table below.

| Topic Suffix          | Payload Type                                      | Description                                                                            |
|-----------------------|---------------------------------------------------|----------------------------------------------------------------------------------------|
| set_volume            | int (0-32)                                        | Set speaker volume                                                                     |
| get_volume            | (empty)                                           | Request current volume                                                                 |
| set_eq_preset         | enum[flat,rock,metal,pop,hiphop,electronic,jazz]  | Set EQ preset                                                                          |
| get_eq_preset         | (empty)                                           | Request current EQ preset, returns "custom" if current profile does not match a preset |
| set_eq_profile        | 5 space delimited integers (0-10)                 | Set EQ profile (`"5 5 5 5 5"`), corresponds to (`160hz 400hz 1khz 2.5khz 6.25khz`)     |
| set_eq_profile/160hz  | int (0-10)                                        | Set EQ value of 160hz, e.g. `"5"`                                                      |
| set_eq_profile/400hz  | int (0-10)                                        | Set EQ value of 400hz, e.g. `"5"`                                                      |
| set_eq_profile/1000hz | int (0-10)                                        | Set EQ value of 1khz, e.g. `"5"`                                                       |
| set_eq_profile/2500hz | int (0-10)                                        | Set EQ value of 2.5khz, e.g. `"5"`                                                     |
| set_eq_profile/6250hz | int (0-10)                                        | Set EQ value of 6.25khz, e.g. `"5"`                                                    |
| get_eq_profile        | (empty)                                           | Request current EQ profile                                                             |
| set_device_name       | str                                               | Set device name                                                                        |
| get_device_name       | (empty)                                           | Request device name                                                                    |
| set_led_brightness    | int (0-35)                                        | Set LED brightness                                                                     |
| get_led_brightness    | (empty)                                           | Request LED brightness                                                                 |
| play                  | (empty)                                           | Start playback                                                                         |
| pause                 | (empty)                                           | Pause playback                                                                         |
| next                  | (empty)                                           | Next track                                                                             |
| previous              | (empty)                                           | Previous track                                                                         |
| set_interaction_sound | int (0/1)                                         | Enable/disable interaction sound                                                       |
| get_status            | (empty)                                           | Request playback/status info                                                           |
| set_source            | enum[bluetooth,aux,rca]                           | Set audio source                                                                       |
| enter_pairing_mode*   | (empty)                                           | Enter Bluetooth pairing mode                                                           |

*Only if pairing is enabled.

### Info/Status Topics

The program publishes status and info to `<prefix>/info/<name>`. Subscribe to these to receive updates.

| Topic Suffix              | Payload Type                                     | Description                                                                                |
|---------------------------|--------------------------------------------------|--------------------------------------------------------------------------------------------|
| volume                    | int                                              | Current volume                                                                             |
| eq_preset                 | enum[flat,rock,metal,pop,hiphop,electronic,jazz] | Current EQ preset, returns "custom" if current profile does not match a preset             |
| eq_profile                | 5 space delimited integers                       | Current EQ profile, e.g. `"5 5 5 5 5"`, corresponds to (`160hz 400hz 1khz 2.5khz 6.25khz`) |
| eq_profile/160hz          | int                                              | Current EQ value of 160hz, e.g. `"5"`                                                      |
| eq_profile/400hz          | int                                              | Current EQ value of 400hz, e.g. `"5"`                                                      |
| eq_profile/1000hz         | int                                              | Current EQ value of 1khz, e.g. `"5"`                                                       |
| eq_profile/2500khz        | int                                              | Current EQ value of 2.5khz, e.g. `"5"`                                                     |
| eq_profile/6250khz        | int                                              | Current EQ value of 6.25khz, e.g. `"5"`                                                    |
| device_name               | str                                              | Current device name                                                                        |
| led_brightness            | int (0 to 35)                                    | Current LED brightness                                                                     |
| play_status               | enum[play, pause, stopped]                       | Playback status                                                                            |
| audio_source              | enum[bluetooth, aux, rca]                        | Current audio source                                                                       |
| interaction_sound_enabled | int (0/1)                                        | 1 if enabled, 0 if not                                                                     |
| media/title               | str                                              | Current media title                                                                        |
| media/artist              | str                                              | Current media artist                                                                       |
| media/album               | str                                              | Current media album                                                                        |

### LWT Topic

The program publishes status and info to `<prefix>/lwt`. Subscribe to this topic to receive updates on connection status.
It will publish `"online"` if connected, `"offline"` if not.
