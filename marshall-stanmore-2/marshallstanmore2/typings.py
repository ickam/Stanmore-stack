import dataclasses
import enum
from typing import TypeAlias, Callable, NamedTuple


@dataclasses.dataclass(eq=True, unsafe_hash=True, slots=True)
class EqProfile:
    hz160: int
    hz400: int
    hz1000: int
    hz2500: int
    hz6250: int

    def __post_init__(self):
        for field in dataclasses.fields(self.__class__):
            if not 0 <= getattr(self, field.name) <= 10:
                raise ValueError(f"{field.name} must be within 0 and 10")

    def __iter__(self):
        return iter(dataclasses.astuple(self))


class EqPreset(enum.Enum):
    FLAT = EqProfile(5, 5, 5, 5, 5)
    ROCK = EqProfile(8, 6, 3, 5, 7)
    METAL = EqProfile(8, 3, 5, 7, 8)
    POP = EqProfile(6, 7, 8, 4, 5)
    HIPHOP = EqProfile(8, 7, 6, 5, 5)
    ELECTRONIC = EqProfile(7, 4, 4, 7, 6)
    JAZZ = EqProfile(4, 7, 5, 4, 5)


class AudioSource(enum.Enum):
    BLUETOOTH = enum.auto()
    AUX = enum.auto()
    RCA = enum.auto()


class PlayStatus(enum.Enum):
    PLAYING = enum.auto()
    PAUSED = enum.auto()
    STOPPED = enum.auto()


class StatusIndex(enum.IntEnum):
    SOURCE = 0
    PLAY_STATUS = 1
    INTERATION_SOUND = 3


class Status(NamedTuple):
    audio_source: AudioSource
    play_status: PlayStatus
    interaction_sound_enabled: bool


AUD_SRC_CMD_MAPPING = {
    AudioSource.BLUETOOTH: 0x0C,
    AudioSource.AUX: 0x0D,
    AudioSource.RCA: 0x0E,
}

CMD_MAPPING = {
    "pause": 0x00,
    "play": 0x01,
    "previous": 0x02,
    "next": 0x03,
    "disable_interation_sound": 0x10,
    "enable_interation_sound": 0x11,
}

INT_PLAY_STATUS_MAPPING = {
    0x00: PlayStatus.PLAYING,
    0x01: PlayStatus.PAUSED,
    0x02: PlayStatus.STOPPED,
}


INT_AUD_SRC_MAPPING = {
    0x03: AudioSource.BLUETOOTH,
    0x01: AudioSource.AUX,
    0x04: AudioSource.RCA,
}


class MediaInfo(NamedTuple):
    title: str | None
    artist: str | None
    album: str | None


IndicationSoundEnabled: TypeAlias = bool
VolumeCallback: TypeAlias = Callable[[int], None]
MediaInfoCallback: TypeAlias = Callable[[MediaInfo], None]
DisconnectCallback: TypeAlias = Callable[[], None]
StatusCallback: TypeAlias = Callable[[Status], None]
EqualizerCallback: TypeAlias = Callable[[EqProfile], None]
