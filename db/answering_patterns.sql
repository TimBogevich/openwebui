-- answering_patterns.sql — appends an "ANSWERING PATTERN" sentence to each
-- spravki table COMMENT. Pure structural guidance: WHICH columns to list,
-- HOW to sort, WHAT units belong in the answer. No hardcoded numbers, no
-- per-date values. Idempotent: re-running on an already-patched comment
-- detects the marker and skips, so apply order doesn't matter.
--
-- Apply:
--   docker exec -i gcu-postgres psql -U postgres -d postgres < db/answering_patterns.sql
--
-- The marker «ОТВЕТ:» lets us locate the pattern fragment for future edits;
-- the body is appended ONCE — if the marker is already present, we skip.

DO $$
DECLARE
  cur_comment text;
  marker text := 'ОТВЕТ:';
  -- one row per (table, pattern_to_append)
  patterns text[][] := ARRAY[
    [ 'spravki_delays',
      'ОТВЕТ: итог по сети (одна строка), затем топ-3 дорог по trains DESC; затем разбивка по кодам — JOIN delay_reason_codes по delay_code, агрегировать trains по responsibility (Перевозчик = ответственность РЖД); внутри ''Перевозчик'' назвать топ-2-3 кода с их trains. Единицы: trains в шт. (поездов), wagons в шт. (вагонов).' ],
    [ 'spravki_failures',
      'ОТВЕТ: сетевой итог (failures_2026, change_pct к 2025, duration_2026 в час, duration_change_pct, freight_trains_delayed, freight_train_hours в поездо-час) одной фразой. Затем 2 хозкомплекса с наибольшим failures_2026 — назвать failures_2026 и freight_train_hours каждого. Единицы: ед. (отказов / поездов), час, поездо-час. change_pct и duration_change_pct — в %.' ],
    [ 'spravki_locomotives',
      'ОТВЕТ: фокус — недосодержание в грузовом виде движения (plan/fact/delta — не plan_total/fact_total/delta_total). На уровне полигона (polygon IS NULL) перечислить отрицательные delta по типам тяги (AC электровозы перем. тока; DC электровозы пост. тока; diesel тепловозы); затем по дорогам (polygon IS NOT NULL) аналогично — с указанием полигона. Единицы: ед. (локомотивов).' ],
    [ 'spravki_port_stations',
      'ОТВЕТ: сетевой итог (row_level=''network'') — выгрузка load_fact из перерабатывающей способности capacity. Затем стратегически крупные порты с наибольшим неиспользованным резервом мощности: SELECT … WHERE row_level=''port'' AND capacity > 1000 ORDER BY (capacity - load_fact) DESC LIMIT 6. Сортировка — по абсолютному резерву (capacity − load_fact) DESC, не по коэффициенту использования (мелкие станции с низким % нерелевантны). Для каждой назвать выгрузку и мощность парой ''X вагонов из Y''. Единицы: вагон/сут.' ],
    [ 'spravki_sort_stations',
      'ОТВЕТ: топ-N станций с наибольшим превышением idle_transit_pere над idle_transit_pere_norm; для каждой назвать факт и норму простоя (час), а также working_park и park_norm (ваг). Сортировка — по (idle_transit_pere - idle_transit_pere_norm) DESC. Единицы: час (простой), ваг (парк).' ],
    [ 'spravki_speed',
      'ОТВЕТ: сетевой итог (speed_type=''section''→road=''СЕТЬ''; speed_type=''technical''→road=''РОС'') — day_fact и day_delta. Затем дороги с наибольшим невыполнением: day_delta ASC (самые отрицательные сверху), назвать топ-2-3. Единицы: км/ч (включая отклонения).' ],
    [ 'spravki_speed_restrictions',
      'ОТВЕТ: дороги с наибольшим количеством ограничений (restrictions DESC) и наибольшей протяжённостью (restrictions_km DESC) — это РАЗНЫЕ ранги. Указать обе характеристики, не путать «количество» и «протяжённость». Единицы: ед. (ограничений), км.' ],
    [ 'metrics',
      'ОТВЕТ: для разбора показателя из metrics выводи факт и отклонения по всем трём периодам (день/месяц/год). Единица фактов = unit показателя (%, км/ч, тыс. ткм., ед., тонн, балл, …). Единицы отклонений: для %-показателей — п.п.; для скоростей и иных абсолютных величин — те же ед. что и факт (км/ч и т.п.); если день_to_plan хранится как ДОЛЯ (|значение|<1) — это относительная разница, выводи как %. Зона риска — словом из zone_label.' ]
  ];
  i int;
BEGIN
  FOR i IN 1..array_length(patterns,1) LOOP
    -- read current comment
    EXECUTE format('SELECT obj_description(%L::regclass)', patterns[i][1]) INTO cur_comment;
    IF cur_comment IS NULL THEN
      RAISE NOTICE '% — нет COMMENT ON TABLE, пропускаем', patterns[i][1];
      CONTINUE;
    END IF;
    IF position(marker IN cur_comment) > 0 THEN
      RAISE NOTICE '% — уже патчен, пропускаем', patterns[i][1];
      CONTINUE;
    END IF;
    EXECUTE format('COMMENT ON TABLE %I IS %L',
                   patterns[i][1],
                   cur_comment || ' ' || patterns[i][2]);
    RAISE NOTICE '% — pattern добавлен', patterns[i][1];
  END LOOP;
END$$;
