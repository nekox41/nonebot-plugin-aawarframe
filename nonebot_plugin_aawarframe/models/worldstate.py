# 作用：实现 models 层的 worldstate 功能。
# 编写日期：2026-11-07
# 作者：Aameow

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, FiniteFloat, model_validator


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


class SortieMission(BaseModel):
    mission_type: str = Field(alias="missionType", min_length=1)
    node: str = Field(min_length=1)
    modifier: str = Field(default="", alias="modifierType")


class Sortie(BaseModel):
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")
    boss: str = Field(alias="Boss")
    variants: list[dict] = Field(default_factory=list, alias="Variants")
    missions: list[dict] = Field(default_factory=list, alias="Missions")


class Invasion(BaseModel):
    activation: WorldDate = Field(alias="Activation")
    node: str = Field(alias="Node", min_length=1)
    attacker: str = Field(alias="Faction")
    defender: str = Field(alias="DefenderFaction")
    count: FiniteFloat = Field(alias="Count")
    goal: FiniteFloat = Field(alias="Goal", gt=0)
    completed: bool = Field(alias="Completed")
    attacker_reward: dict | list = Field(default_factory=dict, alias="AttackerReward")
    defender_reward: dict | list = Field(default_factory=dict, alias="DefenderReward")


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
    job_type: str = Field(default="", alias="jobType")
    is_vault: bool = Field(default=False, alias="isVault")
    endless: bool = False
    location_tag: str = Field(default="", alias="locationTag")
    rewards: str
    xp_amounts: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list, alias="xpAmounts")
    mastery_req: int | None = Field(default=None, alias="masteryReq", ge=0)
    min_level: int = Field(alias="minEnemyLevel")
    max_level: int = Field(alias="maxEnemyLevel")

    @model_validator(mode="after")
    def require_job_type(self):
        if not self.job_type and not self.is_vault:
            raise ValueError("非隔离库赏金缺少任务类型")
        return self


class SyndicateMission(BaseModel):
    tag: str = Field(alias="Tag")
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")
    jobs: list[dict] = Field(default_factory=list, alias="Jobs")
    seed: int | None = Field(default=None, alias="Seed", strict=True)


class Conquest(BaseModel):
    activation: WorldDate | None = Field(default=None, alias="Activation")
    expiry: WorldDate | None = Field(default=None, alias="Expiry")
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
    threshold: int | None = Field(default=None, alias="PointThreshold", ge=0)
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


class NightwaveChallenge(BaseModel):
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")
    challenge: str = Field(alias="Challenge", min_length=1)
    daily: bool = Field(default=False, alias="Daily")


class NightwaveSeason(BaseModel):
    activation: WorldDate | None = Field(default=None, alias="Activation")
    expiry: WorldDate | None = Field(default=None, alias="Expiry")
    challenges: list[dict] = Field(alias="ActiveChallenges")


class CircuitCategory(BaseModel):
    category: str = Field(alias="Category")
    choices: list[str] = Field(alias="Choices", min_length=1)


class CircuitWeek(BaseModel):
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")
    categories: list[CircuitCategory] = Field(alias="CategoryChoices")


class CalendarEvent(BaseModel):
    type: str
    challenge: str | None = None
    reward: str | None = None


class CalendarDay(BaseModel):
    day: int = Field(ge=1, le=365)
    events: list[CalendarEvent]


class CalendarSeason(BaseModel):
    activation: WorldDate = Field(alias="Activation")
    expiry: WorldDate = Field(alias="Expiry")
    days: list[CalendarDay] = Field(alias="Days")
    season: str = Field(alias="Season")
