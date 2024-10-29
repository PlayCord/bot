class Property:
    def __init__(self, uuid=None):
        self.uuid = uuid

    def take(self, uuid):
        self.uuid = uuid
