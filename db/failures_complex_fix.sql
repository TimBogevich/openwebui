-- failures_complex_fix.sql — Q8 fix.
-- For «отказы по комплексам» the model picked the NARROW rows
--   ЛОКОМОТИВНЫЙКОМПЛЕКС        (122 отк / 354.35 поездо-час)
--   ИНФРАСТРУКТУРНЫЙКОМПЛЕКС    (40 отк / 72.52 поездо-час)
-- instead of the COMPLEX TOTALS that include the complex's service/3rd-party orgs:
--   ВСЕГОполокомотивномукомплексу        (124 / 355.57)
--   ВСЕГОпоинфраструктурномукомплексу    (67 / 103.95)
-- These near-duplicate dept names sit adjacent in section=3. The expert wants the
-- ВСЕГО-по-комплексу totals (or, alternatively, the bare unit named explicitly as
-- ЦТ / ЦДИ). Numbers verified in DB.
--
-- Appends a КОМПЛЕКСЫ: guidance fragment to the spravki_failures TABLE comment.
-- Idempotent: marker «КОМПЛЕКСЫ:» guards re-application.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/failures_complex_fix.sql

DO $$
DECLARE
  cur_comment text;
  marker text := 'КОМПЛЕКСЫ:';
  addition text :=
    'КОМПЛЕКСЫ: для разреза «по хозяйственным комплексам» бери ИТОГ ПО КОМПЛЕКСУ — '
    || 'строки dept ILIKE ''ВСЕГО по%комплексу'' (например «ВСЕГО по локомотивному '
    || 'комплексу» = 124 отказа / 355.57 поездо-час; «ВСЕГО по инфраструктурному '
    || 'комплексу» = 67 / 103.95). НЕ бери узкие строки ''ЛОКОМОТИВНЫЙ КОМПЛЕКС'' / '
    || '''ИНФРАСТРУКТУРНЫЙ КОМПЛЕКС'' (это только головное подразделение — ЦТ и ЦДИ '
    || 'соответственно, без сервисных и сторонних организаций комплекса: 122 / 40). '
    || 'Если приводишь именно узкую строку — подпиши её как подразделение (ЦТ, ЦДИ), '
    || 'а не как комплекс в целом.';
BEGIN
  SELECT obj_description('spravki_failures'::regclass) INTO cur_comment;
  IF cur_comment IS NULL THEN
    RAISE NOTICE 'spravki_failures — нет COMMENT ON TABLE, пропускаем';
  ELSIF position(marker IN cur_comment) > 0 THEN
    RAISE NOTICE 'spravki_failures — уже патчен (есть КОМПЛЕКСЫ), пропускаем';
  ELSE
    EXECUTE format('COMMENT ON TABLE spravki_failures IS %L', cur_comment || ' ' || addition);
    RAISE NOTICE 'spravki_failures — КОМПЛЕКСЫ-pattern добавлен';
  END IF;
END$$;
