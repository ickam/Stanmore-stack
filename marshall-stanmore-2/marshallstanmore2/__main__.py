import asyncio
import signal

from ragdoll import env

from marshallstanmore2.mqtt import MqttControl

import logging.config

logger = logging.getLogger("stanmore2.mqtt")


class Settings(env.EnvSetting):
    auto_configure = False

    BLE_ADDRESS = env.StrEnv()
    MQTT_HOSTNAME = env.StrEnv("127.0.0.1")
    MQTT_PORT = env.IntEnv(1883)
    MQTT_USERNAME = env.StrEnv(None)
    MQTT_PASSWORD = env.StrEnv(None)
    MQTT_TOPIC_PREFIX = env.StrEnv("stanmore2")
    MQTT_RETAIN = env.BoolEnv(False)
    ALLOW_PAIRING = env.BoolEnv(False)


async def main() -> int:
    settings = {k.lower(): v for k, v in Settings.configure().items()}
    control = MqttControl(**settings)
    await control.start()
    return 0


def on_sigterm_received(signum, frame):
    logger.info("SIGTERM received")
    raise SystemExit(1)


def connect_signals():
    signal.signal(signal.SIGTERM, on_sigterm_received)


def configure_logging():
    logging.config.dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s.%(msecs)03d][%(name)s][%(levelname)s][%(message)s]",
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "default",
                },
            },
            "loggers": {
                "stanmore2.mqtt": {
                    "level": "INFO",
                    "handlers": ["console"],
                    "propagate": False,
                },
                "stanmore2.ble": {
                    "level": "INFO",
                    "handlers": ["console"],
                    "propagate": False,
                },
            },
        }
    )


if __name__ == "__main__":
    connect_signals()
    configure_logging()
    raise SystemExit(asyncio.run(main()))
