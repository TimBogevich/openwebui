-- source_answer_pattern.sql — Q1 regression fix.
-- On «откуда ты берёшь данные / источник показателя» the model quoted xlsx cell
-- addresses (B10) and FABRICATED «B26 — по дорогам» (no per-road breakdown exists
-- for the срок-доставки indicator: rows_with_road = 0). Correct answer = the RZD
-- source SYSTEMS / справки (КАСАНТ, АРМ ОНД, СИС Эффект, ПК ИУС ЦУП НП, ЕМД ПП УР,
-- АСУ ВОП-2, Доклад СКИМ ОД), i.e. the «ИСТОЧНИК ДЛЯ ОТВЕТА» strings now present in
-- every table comment (db/add_source_systems.py).
--
-- Appends an ИСТОЧНИКИ: answer-pattern to the metrics TABLE comment.
-- Idempotent: marker «ИСТОЧНИКИ:» guards re-application.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/source_answer_pattern.sql

DO $$
DECLARE
  cur_comment text;
  marker text := 'ИСТОЧНИКИ:';
  addition text :=
    'ИСТОЧНИКИ: на вопрос «откуда данные / источник показателя / на основе чего» — '
    || 'назови СИСТЕМЫ-источники и справки ОАО РЖД (из строк «ИСТОЧНИК ДЛЯ ОТВЕТА» в '
    || 'комментариях таблиц: Доклад СКИМ ОД / ЦГЦУ, КАСАНТ, АРМ ОНД, СИС Эффект, '
    || 'ПК ИУС ЦУП НП, ЕМД ПП УР, АСУ ВОП-2), а также перечень показателей-факторов из '
    || 'search_knowledge(''источники данных факторы срок доставки'', collection=''reference''). '
    || 'НЕ называй адреса ячеек xlsx (B10 и т.п.) и НЕ описывай внутреннюю структуру '
    || 'хранения — это не интересует пользователя. НЕ утверждай наличие разбивки по '
    || 'дорогам, не проверив: у показателя доли отправок в срок разбивки по дорогам НЕТ '
    || '(road пустой) — он только сетевой итог.';
BEGIN
  SELECT obj_description('metrics'::regclass) INTO cur_comment;
  IF cur_comment IS NULL THEN
    RAISE NOTICE 'metrics — нет COMMENT ON TABLE, пропускаем';
  ELSIF position(marker IN cur_comment) > 0 THEN
    RAISE NOTICE 'metrics — уже патчен (есть ИСТОЧНИКИ), пропускаем';
  ELSE
    EXECUTE format('COMMENT ON TABLE metrics IS %L', cur_comment || ' ' || addition);
    RAISE NOTICE 'metrics — ИСТОЧНИКИ-pattern добавлен';
  END IF;
END$$;
