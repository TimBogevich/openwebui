-- spravki_comments.sql — Russian COMMENT ON COLUMN for every spravki_* table.
-- Primary fix after the 14.06.2026 РЖД-analyst test run: describe() prints column
-- comments live (mcp_postgres_server.py ~line 305-307), so these comments fix three
-- complaint classes at the metadata layer with NO query logic:
--   1. English column names leaking into answers (load_fact, capacity, row_level…)
--   2. wrong units (speed deviations are км/ч, not «п.п.»)
--   3. double-counting (subtotal/grand-total rows summed with detail rows)
-- Idempotent: COMMENT ON COLUMN is a plain overwrite. Re-run any time.
-- Apply: docker exec -i gcu-postgres psql -U postgres -d postgres < db/spravki_comments.sql

-- ===================== spravki_delays =====================
-- Structure: per-road detail by delay_code, a per-road 'ВСЕГО' subtotal,
-- and a 'СЕТЬ' grand total. Verified 12.03.2026: СЕТЬ/ВСЕГО = 475 поездов / 27 688 ваг.
COMMENT ON COLUMN spravki_delays.delay_code IS 'Код причины задержки. Значение ''ВСЕГО'' — строка-итог по дороге или по сети; числовые коды (1, 5, 2, 43, 22 …) — отдельные причины.';
COMMENT ON COLUMN spravki_delays.delay_name IS 'Расшифровка причины задержки (текст).';
COMMENT ON COLUMN spravki_delays.road_code IS 'Код дороги. Значение ''СЕТЬ'' — строка-итог по всей сети (готовая сумма); прочие коды (ОКТ, ДВС, СКВ …) — отдельные дороги, полное имя в road_codes.';
COMMENT ON COLUMN spravki_delays.trains IS 'Задержано (отставлено) поездов в данной строке. Итог по сети — из строки road_code=''СЕТЬ'',delay_code=''ВСЕГО'' (вьюха v_delays_total), а не суммой детальных строк вручную (риск арифметической ошибки).';
COMMENT ON COLUMN spravki_delays.wagons IS 'Вагонов в задержанных поездах в данной строке. Итог по сети — из строки road_code=''СЕТЬ'',delay_code=''ВСЕГО'' (вьюха v_delays_total).';

-- ===================== spravki_failures =====================
-- Отказы техсредств 1-2 кат. Внимание: таблица содержит ДВЕ секции по dept:
-- (1) ids по дорогам с итогом «Всегопосети» (=234), (2) повторно по дорогам +
-- разбивка по хозяйственным комплексам (вагонный/инфраструктурный/ЦШ…), тоже итог 234.
COMMENT ON COLUMN spravki_failures.dept IS 'Подразделение: либо дорога (Октябрьская, Свердловская…), либо хозяйственный комплекс (ИНФРАСТРУКТУРНЫЙ КОМПЛЕКС, ВАГОННЫЙ КОМПЛЕКС, ЦШ…). ''Всегопосети'' — строка-итог (сумма по дорогам или по комплексам). В таблице две секции (по дорогам и по комплексам), у каждой свой итог ''Всегопосети''; секции — независимые разрезы одних и тех же отказов.';
COMMENT ON COLUMN spravki_failures.failures_2025 IS 'Количество отказов за аналогичный период прошлого года.';
COMMENT ON COLUMN spravki_failures.failures_2026 IS 'Количество отказов в текущем периоде.';
COMMENT ON COLUMN spravki_failures.change_pct IS 'Изменение числа отказов к прошлому году, %.';
COMMENT ON COLUMN spravki_failures.resolved IS 'Устранено отказов.';
COMMENT ON COLUMN spravki_failures.registered IS 'Зарегистрировано (учтено) отказов.';
COMMENT ON COLUMN spravki_failures.investigated IS 'Расследовано отказов.';
COMMENT ON COLUMN spravki_failures.duration_2025 IS 'Суммарная продолжительность отказов за прошлый год, ч.';
COMMENT ON COLUMN spravki_failures.duration_2026 IS 'Суммарная продолжительность отказов в текущем периоде, ч.';
COMMENT ON COLUMN spravki_failures.duration_change_pct IS 'Изменение продолжительности отказов к прошлому году, %.';
COMMENT ON COLUMN spravki_failures.freight_trains_delayed IS 'Задержано грузовых поездов из-за отказов — КОЛИЧЕСТВО поездов, единиц (ЕД., НЕ поездо-часы). По сети 585 = 585 поездов.';
COMMENT ON COLUMN spravki_failures.freight_train_hours IS 'Суммарная ПРОДОЛЖИТЕЛЬНОСТЬ задержки этих поездов, поездо-часов (п/ч). По сети 574,93 п/ч. Это другая величина, чем количество поездов (freight_trains_delayed).';

-- ===================== spravki_port_stations =====================
-- Иерархия в одной таблице через row_level. Верно 12.03.2026: network detained=266,
-- ДВОСТ(road) detained=150. Нет столбцов «накопленный парк» или «коэффициент
-- использования» — их нельзя выдумывать; загрузку считают как load_fact/capacity.
COMMENT ON COLUMN spravki_port_stations.road IS 'Код дороги припортовой станции (ДВОСТ, ОКТ, СКАВ). Полное имя см. road_codes.';
COMMENT ON COLUMN spravki_port_stations.station IS 'Наименование припортовой станции/терминала, либо строка-итог (''ИТОГО ПО ПОРТАМ СЕТИ'', ''ДАЛЬНЕВОСТОЧНАЯ'').';
COMMENT ON COLUMN spravki_port_stations.row_level IS 'Уровень строки: network=итог по сети, road=итог по дороге, port=станция, terminal=терминал, cargo=род груза. Итог по сети — в строках network, по дороге — в road; port/terminal/cargo — детальные уровни, которые уже входят в эти итоги.';
COMMENT ON COLUMN spravki_port_stations.load_total IS 'Погрузка всего за сутки, вагон/сут. Это ПОГРУЗКА, а не план выгрузки; с фактической выгрузкой (load_fact) напрямую не сопоставляется. Плана выгрузки на текущие сутки в справке нет (есть на следующие — unload_plan_next).';
COMMENT ON COLUMN spravki_port_stations.load_fact IS 'Фактическая выгрузка за сутки, вагон/сут. Эффективность порта = load_fact / capacity (использование перерабатывающей способности).';
COMMENT ON COLUMN spravki_port_stations.capacity IS 'Перерабатывающая способность, вагон/сут. Использование перерабатывающей способности = load_fact / capacity.';
COMMENT ON COLUMN spravki_port_stations.wagons_total IS 'Наличие вагонов на станции/в узле, всего.';
COMMENT ON COLUMN spravki_port_stations.wagons_road IS 'В т.ч. вагонов местной дороги.';
COMMENT ON COLUMN spravki_port_stations.detained_trains IS 'Отставленные (задержанные) поезда на уровне данной строки.';
COMMENT ON COLUMN spravki_port_stations.detained_trains_road IS 'В т.ч. отставленные поезда местной дороги.';
COMMENT ON COLUMN spravki_port_stations.load_avg IS 'Средняя выгрузка (за период), вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.unload_avg IS 'Средняя выгрузка/обработка (за период), вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.unload_plan_next IS 'План выгрузки на следующие сутки, вагон/сут.';

-- ===================== spravki_speed =====================
-- Все значения в КМ/Ч, включая отклонения (day_delta/month_delta/year_delta).
-- 'СЕТЬ' в road — строка-итог по сети.
COMMENT ON COLUMN spravki_speed.speed_type IS 'Тип скорости: section=участковая, technical=техническая. Обе в км/ч.';
COMMENT ON COLUMN spravki_speed.road IS 'Дорога. ''СЕТЬ'' — строка-итог по сети. В секции technical коды дорог (ОКТ, СВР…), в section — полные имена.';
COMMENT ON COLUMN spravki_speed.prev_year IS 'Скорость за аналогичный период прошлого года (нарастающим итогом с начала месяца), км/ч. Сопоставляется с month_fact, а не с суточным day_fact.';
COMMENT ON COLUMN spravki_speed.norm IS 'Норма (план) скорости, км/ч.';
COMMENT ON COLUMN spravki_speed.day_fact IS 'Факт за сутки, км/ч. Его отклонение к норме — day_delta.';
COMMENT ON COLUMN spravki_speed.day_delta IS 'Отклонение факта за сутки (day_fact) от нормы, км/ч.';
COMMENT ON COLUMN spravki_speed.month_fact IS 'Факт с начала месяца (нарастающим итогом), км/ч. Его отклонение к норме — month_delta, к прошлому году — year_delta.';
COMMENT ON COLUMN spravki_speed.month_delta IS 'Отклонение факта с начала месяца (month_fact) от нормы, км/ч.';
COMMENT ON COLUMN spravki_speed.year_delta IS 'Отклонение к прошлому году = month_fact − prev_year, км/ч. Считается от МЕСЯЧНОГО факта (нарастающим итогом), НЕ от суточного. В таблице с этим столбцом показывай факт с начала месяца, а не за сутки.';
COMMENT ON COLUMN spravki_speed.nopass_day_fact IS 'Без учёта пассажирского движения: факт за сутки, км/ч.';
COMMENT ON COLUMN spravki_speed.nopass_month_fact IS 'Без пасс.: факт с начала месяца, км/ч.';
COMMENT ON COLUMN spravki_speed.nopass_prev_year IS 'Без пасс.: прошлый год, км/ч.';
COMMENT ON COLUMN spravki_speed.nopass_year_delta IS 'Без пасс.: отклонение к прошлому году, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_day_fact IS 'Пассажирское движение: факт за сутки, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_month_fact IS 'Пасс.: факт с начала месяца, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_prev_year IS 'Пасс.: прошлый год, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_year_delta IS 'Пасс.: отклонение к прошлому году, км/ч.';

-- ===================== spravki_locomotives =====================
COMMENT ON COLUMN spravki_locomotives.section IS 'Тип тяги: AC=переменный ток, DC=постоянный ток, diesel=тепловозы.';
COMMENT ON COLUMN spravki_locomotives.polygon IS 'Тяговый полигон, к которому относится строка-дорога. NULL означает, что сама строка является итогом по полигону (поле road в такой строке = название полигона: Восточный, Северо-Западный, Юго-Западный, Московский, Октябрьский). Не-NULL означает, что строка — отдельная дорога ВНУТРИ указанного полигона.';
COMMENT ON COLUMN spravki_locomotives.road IS 'В строках polygon IS NULL — название тягового полигона (Восточный, Северо-Западный, …) — это уровень итога. В строках polygon=non-NULL — код дороги внутри полигона (В-СИБ, ДВОСТ, ЗАБ, КРАС, ОКТ, СЕВ, …); расшифровка через JOIN road_codes. Итоги по полигону и детальные строки дорог под ним — разные уровни, складывать их вместе нельзя.';
COMMENT ON COLUMN spravki_locomotives.plan IS 'План эксплуатируемого парка локомотивов (по типу тяги).';
COMMENT ON COLUMN spravki_locomotives.fact IS 'Факт эксплуатируемого парка (по типу тяги).';
COMMENT ON COLUMN spravki_locomotives.delta IS 'Отклонение факт−план (по типу тяги), локомотивов.';
COMMENT ON COLUMN spravki_locomotives.plan_total IS 'План парка, всего по строке.';
COMMENT ON COLUMN spravki_locomotives.fact_total IS 'Факт парка, всего по строке.';
COMMENT ON COLUMN spravki_locomotives.delta_total IS 'Отклонение факт−план, всего, локомотивов.';
COMMENT ON COLUMN spravki_locomotives.reserve IS 'Локомотивы в резерве.';

-- ===================== spravki_sort_stations =====================
-- Работа важнейших сортировочных станций. Нет столбца «расформировано» отдельно —
-- роспуск/формирование см. rosp_total / formed_trains.
COMMENT ON COLUMN spravki_sort_stations.road IS 'Код дороги станции.';
COMMENT ON COLUMN spravki_sort_stations.station IS 'Сортировочная станция (ЮДИНО, ДЕМА, ПЕРМЬ-СОРТ …).';
COMMENT ON COLUMN spravki_sort_stations.period IS 'Период (''сут.'' — за сутки).';
COMMENT ON COLUMN spravki_sort_stations.working_park IS 'Рабочий парк вагонов на станции (факт).';
COMMENT ON COLUMN spravki_sort_stations.park_norm IS 'Норматив рабочего парка.';
COMMENT ON COLUMN spravki_sort_stations.rosp_total IS 'Распущено (расформировано) вагонов с горки, всего.';
COMMENT ON COLUMN spravki_sort_stations.rosp_no_pere IS 'Распущено без переработки.';
COMMENT ON COLUMN spravki_sort_stations.arrived_trains IS 'Прибыло поездов.';
COMMENT ON COLUMN spravki_sort_stations.refused_trains IS 'Отклонено (брошено/не принято) поездов.';
COMMENT ON COLUMN spravki_sort_stations.formed_trains IS 'Сформировано составов.';
COMMENT ON COLUMN spravki_sort_stations.sent_trains IS 'Отправлено поездов.';
COMMENT ON COLUMN spravki_sort_stations.avg_weight IS 'Средний вес состава, т.';
COMMENT ON COLUMN spravki_sort_stations.avg_length IS 'Средняя длина состава, усл. ваг.';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_pere IS 'Простой транзитного вагона с переработкой, ч.';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_pere_norm IS 'Норматив простоя транзитного вагона с переработкой, ч.';

-- ===================== spravki_speed_restrictions =====================
-- Ограничения скорости, не предусмотренные ГДП. 'Итого по сети' — строка-итог.
COMMENT ON COLUMN spravki_speed_restrictions.road IS 'Дорога. ''Итого по сети'' — строка-ИТОГ по сети.';
COMMENT ON COLUMN spravki_speed_restrictions.row_type IS 'Тип строки (''fact'' — фактические ограничения).';
COMMENT ON COLUMN spravki_speed_restrictions.restrictions IS 'Количество ограничений скорости, ед.';
COMMENT ON COLUMN spravki_speed_restrictions.restrictions_km IS 'Протяжённость участков с ограничениями, км.';
COMMENT ON COLUMN spravki_speed_restrictions.ratio_pct IS 'Доля от развёрнутой длины, %.';
COMMENT ON COLUMN spravki_speed_restrictions.delta_km IS 'Изменение протяжённости ограничений, км.';
