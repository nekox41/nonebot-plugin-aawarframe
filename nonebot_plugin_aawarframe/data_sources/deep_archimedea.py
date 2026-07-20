from .conquest_base import ConquestDataSource

class DeepArchimedeaSource(ConquestDataSource):
    @property
    def command_name(self) -> str:
        return "deep_archimedea"

    @property
    def conquest_type(self) -> str:
        return "CT_LAB"