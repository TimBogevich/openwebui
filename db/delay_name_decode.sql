-- delay_name_decode.sql — fix the «п.сост.» hallucination.
-- spravki_delays.delay_name stores ABBREVIATED reason text («Вр. размещ. п.сост.»).
-- «п.сост.» = подвижного состава (rolling stock), but the model expanded it to
-- «пассажирских составов» (passenger trains) — a wrong guess from the abbreviation.
-- The full official wording lives in delay_reason_codes (matches the source xlsx
-- «Коды бросаний для справки»). This appends a NAMING: hint telling the model to
-- take the answer text from the classifier, never from the short delay_name.
-- (The describe() value-list now also decodes each code to its full name — same
-- live-JOIN trick as road_codes; this comment reinforces it.)
--
-- Idempotent: marker «NAMING:» guards re-application.
-- Apply: docker exec -i gcu-postgres psql -U postgres -d postgres < db/delay_name_decode.sql

DO $$
DECLARE
  cur_comment text;
  marker text := 'NAMING:';
  addition text :=
    'NAMING: колонка delay_name — СОКРАЩЕНИЕ («Вр. размещ. п.сост.», «Неприем грузопол» …). '
    || 'Для ТЕКСТА ОТВЕТА бери полное официальное название из delay_reason_codes '
    || '(JOIN по delay_code → reason_name/full_description), НЕ разворачивай сокращение сам. '
    || 'В частности «п.сост.» = подвижного состава (НЕ пассажирских составов): код 5 = '
    || '«Оказание услуг по временному размещению собственного (арендованного) подвижного '
    || 'состава» — это платная услуга по договору с грузовладельцем, а не пассажирские поезда.';
BEGIN
  SELECT obj_description('spravki_delays'::regclass) INTO cur_comment;
  IF cur_comment IS NULL THEN
    RAISE NOTICE 'spravki_delays — нет COMMENT ON TABLE, пропускаем';
  ELSIF position(marker IN cur_comment) > 0 THEN
    RAISE NOTICE 'spravki_delays — уже патчен (есть NAMING), пропускаем';
  ELSE
    EXECUTE format('COMMENT ON TABLE spravki_delays IS %L', cur_comment || ' ' || addition);
    RAISE NOTICE 'spravki_delays — NAMING-pattern добавлен';
  END IF;
END$$;
