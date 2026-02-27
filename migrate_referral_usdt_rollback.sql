-- Emergency rollback for referral_rewards + users.usdt_withdraw_address + withdrawal_requests.rejection_note
-- Run only if you need to undo migrate_referral_usdt.py. This drops referral_rewards and removes added columns.

-- Drop referral_rewards (will lose reward history)
DROP TABLE IF EXISTS referral_rewards;

-- Remove column from users (optional; comment out if you want to keep the column)
-- ALTER TABLE users DROP COLUMN IF EXISTS usdt_withdraw_address;

-- Remove column from withdrawal_requests (optional)
-- ALTER TABLE withdrawal_requests DROP COLUMN IF EXISTS rejection_note;
