from .conquest_base import ConquestDataSource

class TemporalArchimedeaSource(ConquestDataSource):
    @property
    def command_name(self) -> str:
        return "temporal_archimedea"

    @property
    def conquest_type(self) -> str:
        return "CT_HEX"