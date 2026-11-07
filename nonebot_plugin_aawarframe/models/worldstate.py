from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field


def parse_date(value: Any) -> datetime:
    if isinstance(value, dict):
        value = value.get("$date", value)
        if isinstance(value, dict):
            value = value["$numberLong"]
        return datetime.fromtimestamp(int(value) / 1000, timezone.utc)
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        number = float(value)
        return datetime.fromtimestamp(number / 1000 if number > 10**11 else number, timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(timezone.utc)


WorldDate = Annotated[datetime, BeforeValidator(parse_date)]


class TimedMission(BaseModel):
    node: str = Field(alias="Node")
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")


class Fissure(TimedMission):
    modifier: str = Field(alias="Modifier")
    hard: bool = Field(default=False, alias="Hard")


class VoidStorm(TimedMission):
    modifier: str = Field(alias="ActiveMissionTier")


class SyndicateJob(BaseModel):
    job_type: str = Field(alias="jobType")
    rewards: str
    min_level: int = Field(alias="minEnemyLevel")
    max_level: int = Field(alias="maxEnemyLevel")


class SyndicateMission(BaseModel):
    tag: str = Field(alias="Tag")
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")
    jobs: list[dict] = Field(default_factory=list, alias="Jobs")


class Conquest(BaseModel):
    type: str = Field(alias="Type")
    missions: list[dict] = Field(alias="Missions")
    variables: list[str] = Field(default_factory=list, alias="Variables")


class Difficulty(BaseModel):
    type: str
    deviation: str | None = None
    risks: list[str] = Field(default_factory=list)


class ConquestMission(BaseModel):
    faction: str
    mission_type: str = Field(alias="missionType")
    difficulties: list[Difficulty]


class VaultReward(BaseModel):
    reward: str = Field(alias="Reward")
    count: int = Field(alias="ItemCount", ge=0)


class VaultWeek(BaseModel):
    week: int = Field(alias="WeekCount")
    region: str = Field(alias="BonusRegion")
    rewards: list[VaultReward] = Field(alias="Rewards")


class CycleState(BaseModel):
    location: str
    state: str
    next_state: str
    expiry: datetime
    basis: str
