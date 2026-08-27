from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from .translator import translate
import time

class WeeklyVaultReward(BaseModel):
    RewardClaimed: bool
    PointThreshold: int
    ItemCount: int
    Reward: str

    async def reward_name(self) -> str:
        """获取翻译后的奖励名称"""
        return await translate(self.Reward)

class WeeklyVaultBonus(BaseModel):
    WeekCount: int
    BonusRegion: str
    Rewards: List[WeeklyVaultReward]

    async def region_name(self) -> str:
        """获取翻译后的地区名称"""
        return await translate(self.BonusRegion)

# ------ 赏金 （SyndicateMissions）
class SyndicateJob(BaseModel):
    jobType: Optional[str] = None
    rewards: str
    masteryReq: int
    minEnemyLevel: int
    maxEnemyLevel: int
    xpAmounts: List[int]
    locationTag: Optional[str] = None
    isVault: Optional[bool] = False
    endless: Optional[bool] = False


class SyndicateMission(BaseModel):
    _id: str
    Activation: int
    Expiry: int
    Tag: str
    Seed: int
    Nodes: List[str]
    Jobs: Optional[List[SyndicateJob]] = None


    @field_validator('_id', mode='before', check_fields=False)
    @classmethod
    def extract_oid(cls, v):
        """处理 { '$oid': '...' } 或直接字符串"""
        if isinstance(v, dict) and '$oid' in v:
            return v['$oid']
        return v

    @field_validator('Activation', 'Expiry', mode='before')
    @classmethod
    def extract_numberlong(cls, v):
        """处理 { '$date': { '$numberLong': '...' } } 或直接数字"""
        if isinstance(v, dict) and '$date' in v:
            date_val = v['$date']
            if isinstance(date_val, dict) and '$numberLong' in date_val:
                return int(date_val['$numberLong'])   # 转为 int
        return v

    def is_valid(self) -> bool:
        """检查任务是否仍然有效（未过期）"""
        now_ms = int(time.time() * 1000)   # 当前毫秒时间戳
        return self.Activation < now_ms < self.Expiry  # 当前时间小于过期时间 => 有效

class WorldState(BaseModel):
    model_config = ConfigDict(extra='ignore')
    WeeklyVaultBonusRewards: List[WeeklyVaultBonus]
    SyndicateMissions: List[SyndicateMission]
