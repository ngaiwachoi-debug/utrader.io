"""
3-level referral USDT Credit rewards. Applied when a user burns purchased tokens only.
Rates: L1=0.0015, L2=0.0005, L3=0.0001 USDT Credit per token.
No recursion: max 3 DB lookups for uplines.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

import models

REWARD_L1 = 0.0015
REWARD_L2 = 0.0005
REWARD_L3 = 0.0001


def apply_referral_rewards(
    db: Session,
    burning_user_id: int,
    purchased_tokens_burned: float,
) -> None:
    """
    Credit L1/L2/L3 uplines with USDT Credit for purchased token burn.
    Atomic: either all levels get rewards or none. No recursion (3 direct lookups).
    """
    if purchased_tokens_burned <= 0:
        return
    burning_user = db.query(models.User).filter(models.User.id == burning_user_id).first()
    if not burning_user:
        return
    level_1_id: Optional[int] = burning_user.referred_by
    level_2_id: Optional[int] = None
    level_3_id: Optional[int] = None
    if level_1_id:
        u1 = db.query(models.User).filter(models.User.id == level_1_id).first()
        if u1:
            level_2_id = u1.referred_by
    if level_2_id:
        u2 = db.query(models.User).filter(models.User.id == level_2_id).first()
        if u2:
            level_3_id = u2.referred_by

    reward_l1 = round(purchased_tokens_burned * REWARD_L1, 6)
    reward_l2 = round(purchased_tokens_burned * REWARD_L2, 6)
    reward_l3 = round(purchased_tokens_burned * REWARD_L3, 6)

    now = datetime.utcnow()
    db.add(models.ReferralReward(
        burning_user_id=burning_user_id,
        level_1_id=level_1_id,
        level_2_id=level_2_id,
        level_3_id=level_3_id,
        reward_l1=reward_l1,
        reward_l2=reward_l2,
        reward_l3=reward_l3,
        created_at=now,
    ))

    def credit_user(uid: Optional[int], amount: float) -> None:
        if uid is None or amount <= 0:
            return
        uc = db.query(models.UserUsdtCredit).filter(models.UserUsdtCredit.user_id == uid).first()
        if not uc:
            uc = models.UserUsdtCredit(user_id=uid, usdt_credit=0.0, total_earned=0.0, total_withdrawn=0.0)
            db.add(uc)
        uc.usdt_credit = float(uc.usdt_credit or 0) + amount
        uc.total_earned = float(uc.total_earned or 0) + amount
        uc.updated_at = now
        db.add(models.UsdtHistory(user_id=uid, amount=amount, reason="referral_earnings", admin_email=None))

    credit_user(level_1_id, reward_l1)
    credit_user(level_2_id, reward_l2)
    credit_user(level_3_id, reward_l3)
