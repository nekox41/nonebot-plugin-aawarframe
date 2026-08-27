from .cache import clan_weekly_cache
from ...integrations.world_state import fetch_world_state

async def gen_clan_weekly_img():
    cached_data = clan_weekly_cache.get()
    if cached_data is None:
        data = await fetch_world_state()
        await clan_weekly_cache.set(data.WeeklyVaultBonusRewards)

    cached_data = clan_weekly_cache.get()
    this_week = cached_data[0]
    next_week = cached_data[1]
    for reward in this_week.Rewards:
        if reward.Reward == "/Lotus/StoreItems/Upgrades/Mods/FusionBundles/UncommonFusionBundle":
            reward.ItemCount *= 50
    for reward in next_week.Rewards:
        if reward.Reward == "/Lotus/StoreItems/Upgrades/Mods/FusionBundles/UncommonFusionBundle":
            reward.ItemCount *= 50

    return f"""本周氏族奖励
    双倍区域：{this_week.region_name()}
    奖励1：{this_week.Rewards[0].ItemCount}x {this_week.Rewards[0].reward_name()}
    奖励2：{this_week.Rewards[1].ItemCount}x {this_week.Rewards[1].reward_name()}
    奖励3：{this_week.Rewards[2].ItemCount}x {this_week.Rewards[2].reward_name()}
    奖励4：{this_week.Rewards[3].ItemCount}x {this_week.Rewards[3].reward_name()}
    
    下周氏族奖励
    双倍区域：{next_week.region_name()}
    奖励1：{next_week.Rewards[0].ItemCount}x {await next_week.Rewards[0].reward_name()}
    奖励2：{next_week.Rewards[1].ItemCount}x {await next_week.Rewards[1].reward_name()}
    奖励3：{next_week.Rewards[2].ItemCount}x {await next_week.Rewards[2].reward_name()}
    奖励4：{next_week.Rewards[3].ItemCount}x {await next_week.Rewards[3].reward_name()}
    """