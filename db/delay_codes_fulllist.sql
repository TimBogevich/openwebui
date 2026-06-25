-- delay_codes_fulllist.sql — teach the model to list the FULL 40-code classifier
-- when asked «коды задержек / справочник кодов / какие коменклатура кодов / расшифровка»,
-- instead of only the ~12 codes that happen to appear in spravki_delays for a date.
-- Also reinforces: «коды на <дата>» = JOIN со spravki_delays по этой дате.
--
-- Pure data-layer guidance appended to the delay_reason_codes TABLE comment.
-- Idempotent: marker «ОТВЕТ:» guards re-application.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/delay_codes_fulllist.sql

DO $$
DECLARE
  cur_comment text;
  marker text := 'ОТВЕТ:';
  addition text :=
    'ОТВЕТ: на запрос списка/перечня/справочника/классификатора кодов задержек '
    || '(«коды задержек», «справочник кодов», «какие есть коды», «расшифровка кодов») — '
    || 'выведи ВЕСЬ классификатор из этой таблицы, а не только коды, встретившиеся за конкретную дату: '
    || 'SELECT delay_code, reason_name, responsibility FROM delay_reason_codes ORDER BY (delay_code)::int. '
    || 'Это 40 кодов (1–95 с пропусками). Если спрашивают «коды на <дата>» / «сколько по каждому коду» — '
    || 'тогда JOIN со spravki_delays по этой дате (delay_code), но справочник причин остаётся полным. '
    || 'Группировка по ответственности: Перевозчик (ответственность ОАО РЖД) — коды с responsibility=''Перевозчик''; '
    || 'внешние — Грузоотправитель/Грузополучатель/Оператор ПС и Третьи лица/Сторонние организации.';
BEGIN
  SELECT obj_description('delay_reason_codes'::regclass) INTO cur_comment;
  IF cur_comment IS NULL THEN
    RAISE NOTICE 'delay_reason_codes — нет COMMENT ON TABLE, пропускаем';
  ELSIF position(marker IN cur_comment) > 0 THEN
    RAISE NOTICE 'delay_reason_codes — уже патчен (есть ОТВЕТ), пропускаем';
  ELSE
    EXECUTE format('COMMENT ON TABLE delay_reason_codes IS %L',
                   cur_comment || ' ' || addition);
    RAISE NOTICE 'delay_reason_codes — ОТВЕТ-pattern добавлен';
  END IF;
END$$;
