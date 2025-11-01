class MarshallException(Exception):
    pass


class InvalidVolume(MarshallException):
    pass


class InvalidLedBrightness(MarshallException):
    pass


class InvalidDeviceName(MarshallException):
    pass


class InvalidCallbackID(MarshallException):
    pass
