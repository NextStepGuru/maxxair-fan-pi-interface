from maxxair_fan import firebase


class FirebaseRestBackend:
    def get(self, path: str):
        return firebase.fb_get(path)

    def patch(self, path: str, data: dict) -> bool:
        return firebase.fb_patch(path, data)
