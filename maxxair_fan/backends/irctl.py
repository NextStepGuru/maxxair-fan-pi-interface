from maxxair_fan import fan


class IrCtlBackend:
    def send(self, filename: str) -> bool:
        return fan.send_ir(filename)
