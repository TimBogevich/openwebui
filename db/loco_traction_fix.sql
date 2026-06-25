-- loco_traction_fix.sql — Q7 fix.
-- Expert: the answer must NOT collapse the deficit into a single «211 ед» total;
-- it must be split by traction type — electric by current (AC=переменный,
-- DC=постоянный) and diesel (тепловозы). The existing ОТВЕТ already says "по типам
-- тяги", but the model still reported one summed polygon number and a grand total.
-- This appends an explicit "no cross-traction sum" rule.
--
-- Appends a ТЯГА: guidance fragment to the spravki_locomotives TABLE comment.
-- Idempotent: marker «ТЯГА:» guards re-application.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/loco_traction_fix.sql

DO $$
DECLARE
  cur_comment text;
  marker text := 'ТЯГА:';
  addition text :=
    'ТЯГА: основной показатель — недосодержание в ГРУЗОВОМ движении, колонки '
    || 'plan/fact/delta (НЕ plan_total/fact_total/delta_total — это весь парк с '
    || 'резервом, для этого вопроса НЕ годится). Покажи дефицит ОТДЕЛЬНО по каждому '
    || 'типу тяги: электровозы переменного тока (section=AC), электровозы постоянного '
    || 'тока (section=DC), тепловозы (section=diesel). Сетевой итог по грузовому '
    || 'движению: AC delta=-113, DC delta=+48, diesel delta=-65. НЕ своди к одному '
    || 'суммарному числу и НЕ бери *_total — там другие цифры (AC -55, DC +113, '
    || 'diesel +34), которые отвечают на другой вопрос.';
BEGIN
  SELECT obj_description('spravki_locomotives'::regclass) INTO cur_comment;
  IF cur_comment IS NULL THEN
    RAISE NOTICE 'spravki_locomotives — нет COMMENT ON TABLE, пропускаем';
  ELSIF position(marker IN cur_comment) > 0 THEN
    RAISE NOTICE 'spravki_locomotives — уже патчен (есть ТЯГА), пропускаем';
  ELSE
    EXECUTE format('COMMENT ON TABLE spravki_locomotives IS %L', cur_comment || ' ' || addition);
    RAISE NOTICE 'spravki_locomotives — ТЯГА-pattern добавлен';
  END IF;
END$$;
