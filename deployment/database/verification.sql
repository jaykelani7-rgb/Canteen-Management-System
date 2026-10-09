-- psql-only, read-only verification for the current fully migrated schema.
-- Store the output privately. Compare a frozen source snapshot with its restore.
\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT version_num AS migration_revision FROM public.alembic_version ORDER BY version_num;
SELECT format('SELECT %L AS table_name, count(*) AS row_count FROM %I.%I;', tablename, schemaname, tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
\gexec
SELECT count(*) AS students, coalesce(sum(wallet_balance), 0) AS wallet_total,
       coalesce(sum(total_spent), 0) AS total_spent
FROM public.students;
SELECT count(*) AS orders, coalesce(sum(total_amount), 0) AS order_total FROM public.orders;
SELECT transaction_type, status, count(*) AS entries, coalesce(sum(amount), 0) AS amount
FROM public.wallet_transactions GROUP BY transaction_type, status ORDER BY transaction_type, status;
SELECT count(*) AS invalid_token_balances FROM public.mess_subscriptions
WHERE remaining_tokens < 0 OR remaining_tokens > total_tokens;
SELECT count(*) AS mess_balance_mismatches
FROM public.mess_subscriptions s
LEFT JOIN (SELECT subscription_id, count(*) AS used FROM public.mess_meal_attendance WHERE status = 'Taken' GROUP BY subscription_id) a
ON a.subscription_id = s.id
WHERE s.total_tokens - s.remaining_tokens <> coalesce(a.used, 0);
SELECT count(*) AS duplicate_taken_meals FROM (
  SELECT subscription_id, meal_date, meal_type FROM public.mess_meal_attendance
  WHERE status = 'Taken' GROUP BY subscription_id, meal_date, meal_type HAVING count(*) > 1
) AS duplicates;
SELECT count(*) AS invalid_attendance_ledger FROM public.mess_meal_attendance
WHERE token_before <= 0 OR token_after <> token_before - 1
   OR (status = 'Reversed' AND (reversed_at IS NULL OR reversal_token_before IS NULL
       OR reversal_token_after IS NULL OR reversal_token_after <> reversal_token_before + 1));
SELECT state, purpose, count(*) AS intents, coalesce(sum(amount_paise), 0) AS amount_paise
FROM public.payment_intents GROUP BY state, purpose ORDER BY state, purpose;
SELECT state, count(*) AS refunds, coalesce(sum(amount_paise), 0) AS amount_paise
FROM public.payment_refunds GROUP BY state ORDER BY state;
SELECT count(*) AS invalidated_constraints FROM pg_constraint
WHERE connamespace = 'public'::regnamespace AND NOT convalidated;
COMMIT;
