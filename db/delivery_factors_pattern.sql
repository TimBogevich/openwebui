-- delivery_factors_pattern.sql — Issue 1 fix.
-- When the user asks a QUALITATIVE «какие основные причины и факторы повлияли на
-- невыполнение показателя доставки в срок», the model must answer with the
-- structured FACTOR TAXONOMY (6 groups) tied to the rise in detained trains —
-- NOT dump the spravki_delays code table, and NOT just continue the previous
-- turn's numeric context. The taxonomy already lives in kb_chunks collection
-- 'reference' (ids 3365-3372, 3577); this pattern routes the model to it.
--
-- Data-layer: append a qualitative-vs-quantitative split to spravki_delays
-- TABLE comment (the table find_indicator routes срок-доставки-cause questions to).
-- Idempotent: marker «ФАКТОРЫ:» guards re-application.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/delivery_factors_pattern.sql

DO $$
DECLARE
  cur_comment text;
  marker text := 'ФАКТОРЫ:';
  addition text :=
    'ФАКТОРЫ: различай два типа вопроса. (1) КАЧЕСТВЕННЫЙ — «какие основные причины и '
    || 'факторы повлияли на невыполнение показателя доставки в срок» — отвечай '
    || 'структурированным перечнем групп факторов (соблюдение скорости и графика движения; '
    || 'простои на технических и сортировочных станциях; обеспечение тягой и недосодержание '
    || 'локомотивов; работа портов и грузовые операции; инфраструктурные ограничения скорости; '
    || 'отказы технических средств; внешние участники — грузополучатели, порты, погранпереходы), '
    || 'связав с ростом числа отставленных поездов. Таксономию бери из '
    || 'search_knowledge(''причины и факторы невыполнения срок доставки'', collection=''reference''). '
    || 'Сырой перечень кодов из spravki_delays в этом случае НЕ выводи, если про цифры по кодам '
    || 'не спросили отдельно. (2) КОЛИЧЕСТВЕННЫЙ — «приведи цифры / по кодам / сколько поездов» — '
    || 'тогда таблица spravki_delays по кодам (см. ОТВЕТ выше).';
BEGIN
  SELECT obj_description('spravki_delays'::regclass) INTO cur_comment;
  IF cur_comment IS NULL THEN
    RAISE NOTICE 'spravki_delays — нет COMMENT ON TABLE, пропускаем';
  ELSIF position(marker IN cur_comment) > 0 THEN
    RAISE NOTICE 'spravki_delays — уже патчен (есть ФАКТОРЫ), пропускаем';
  ELSE
    EXECUTE format('COMMENT ON TABLE spravki_delays IS %L',
                   cur_comment || ' ' || addition);
    RAISE NOTICE 'spravki_delays — ФАКТОРЫ-pattern добавлен';
  END IF;
END$$;
