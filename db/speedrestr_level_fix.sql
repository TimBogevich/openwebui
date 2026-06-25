-- speedrestr_level_fix.sql — Q6 fix.
-- Expert: rank/​present each road by its «уровень» FIRST (доля факта от плана =
-- ratio_pct in the row_type='plan' rows), THEN add length. Ranking purely by km
-- is misleading: Свердловская has the most km (257) but is WITHIN its plan
-- (уровень 87%), whereas Горьковская is OVER plan (189%) — the real concern.
-- ratio_pct = факт/план в %; >100% = превышение планового уровня.
--
-- Appends an УРОВЕНЬ: guidance fragment to spravki_speed_restrictions TABLE comment.
-- Idempotent: marker «УРОВЕНЬ:» guards re-application.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/speedrestr_level_fix.sql

DO $$
DECLARE
  cur_comment text;
  marker text := 'УРОВЕНЬ:';
  addition text :=
    'УРОВЕНЬ: у каждой дороги есть плановый уровень ограничений. ratio_pct (в строках '
    || 'row_type=''plan'') = доля факта от планового уровня, %: >100 = превышение '
    || '(дорога-нарушитель), <=100 = в пределах плана. РЕЦЕПТ: фактические ограничения '
    || 'бери из row_type=''fact'' (последняя дата), плановый уровень и ratio_pct — из '
    || 'row_type=''plan'' той же дороги (JOIN по road). Сначала перечисли дороги с '
    || 'ratio_pct>100 (Горьковская 189%, Северо-Кавказская 103%) — это основные '
    || 'нарушители; затем дороги с наибольшей протяжённостью (restrictions_km). Дорога '
    || 'с большим километражом, но в пределах планового уровня (Свердловская: 257 км, '
    || 'уровень 87%), НЕ ставится первой — отметь, что план не превышен. Не уходи в '
    || 'metrics/report_comments — все данные здесь.';
BEGIN
  SELECT obj_description('spravki_speed_restrictions'::regclass) INTO cur_comment;
  IF cur_comment IS NULL THEN
    RAISE NOTICE 'spravki_speed_restrictions — нет COMMENT ON TABLE, пропускаем';
  ELSIF position(marker IN cur_comment) > 0 THEN
    RAISE NOTICE 'spravki_speed_restrictions — уже патчен (есть УРОВЕНЬ), пропускаем';
  ELSE
    EXECUTE format('COMMENT ON TABLE spravki_speed_restrictions IS %L', cur_comment || ' ' || addition);
    RAISE NOTICE 'spravki_speed_restrictions — УРОВЕНЬ-pattern добавлен';
  END IF;
END$$;
