from maxxair_fan import fan


class IrCtlBackend:
    def __init__(self, ir_device: str | None = None) -> None:
        self.ir_device = ir_device

    def send(self, filename: str) -> bool:
        return fan.send_ir(filename, ir_device=self.ir_device)
