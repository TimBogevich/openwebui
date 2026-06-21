-- spravki_comments.sql — COMMENT ON COLUMN для всех spravki_* таблиц.
-- Применение: docker exec -i gcu-postgres psql -U postgres -d postgres < db/spravki_comments.sql

-- ===================== spravki_delays =====================
-- Структура: деталь по дорогам и кодам причин, подытог ВСЕГО по дороге,
-- итог СЕТЬ по всей сети.
COMMENT ON COLUMN spravki_delays.delay_code IS 'Код причины задержки. Значение ВСЕГО — подытог по дороге или по сети; числовые коды (1, 5, 2, 43, 22 …) — отдельные причины.';
COMMENT ON COLUMN spravki_delays.delay_name IS 'Расшифровка причины задержки (текст).';
COMMENT ON COLUMN spravki_delays.road_code IS 'Код дороги. СЕТЬ — итог по всей сети; прочие коды (ОКТ, ДВС, СКВ …) — отдельные дороги; полное имя в road_codes.';
COMMENT ON COLUMN spravki_delays.trains IS 'Количество задержанных (отставленных) поездов в данной строке.';
COMMENT ON COLUMN spravki_delays.wagons IS 'Количество вагонов в задержанных поездах в данной строке.';

-- ===================== spravki_failures =====================
-- Отказы техсредств 1-2 категории. Таблица содержит ТРИ раздела (колонка section):
-- section=1 — отказы, ПРОИЗОШЕДШИЕ на территории дороги (с итогом Всегопосети);
-- section=2 — отказы ПО ОТВЕТСТВЕННОСТИ подразделений дороги (с итогом Всегопосети);
-- section=3 — разбивка по хозяйственным комплексам (вагонный/инфраструктурный/локомотивный).
-- Одна дорога есть в section 1 И 2 с РАЗНЫМИ значениями; каждый раздел независимо
-- суммируется в сетевой итог — НИКОГДА не складывай разделы между собой (задвоишь).
COMMENT ON COLUMN spravki_failures.section IS '1=произошедшие на территории дороги; 2=по ответственности подразделений; 3=по хозяйственным комплексам. Каждый раздел сам суммируется в сетевой ИТОГО — НЕ складывать разделы.';
COMMENT ON COLUMN spravki_failures.dept IS 'Подразделение: дорога (Октябрьская, Свердловская …) или хозяйственный комплекс (ИНФРАСТРУКТУРНЫЙ, ВАГОННЫЙ, ЛОКОМОТИВНЫЙ …). Всегопосети — строка-итог (сумма по строкам данного раздела section).';
COMMENT ON COLUMN spravki_failures.failures_2025 IS 'Число отказов за аналогичный период прошлого года.';
COMMENT ON COLUMN spravki_failures.failures_2026 IS 'Число отказов в текущем периоде.';
COMMENT ON COLUMN spravki_failures.change_pct IS 'Изменение числа отказов к прошлому году, %.';
COMMENT ON COLUMN spravki_failures.resolved IS 'Число устранённых отказов.';
COMMENT ON COLUMN spravki_failures.registered IS 'Число зарегистрированных отказов.';
COMMENT ON COLUMN spravki_failures.investigated IS 'Число расследованных отказов.';
COMMENT ON COLUMN spravki_failures.duration_2025 IS 'Суммарная продолжительность отказов за прошлый год, ч.';
COMMENT ON COLUMN spravki_failures.duration_2026 IS 'Суммарная продолжительность отказов в текущем периоде, ч.';
COMMENT ON COLUMN spravki_failures.duration_change_pct IS 'Изменение суммарной продолжительности отказов к прошлому году, %.';
COMMENT ON COLUMN spravki_failures.freight_trains_delayed IS 'Количество грузовых поездов, задержанных из-за отказов, ед.';
COMMENT ON COLUMN spravki_failures.freight_train_hours IS 'Суммарная продолжительность задержки грузовых поездов из-за отказов, поездо-часов.';

-- ===================== spravki_port_stations =====================
-- Иерархия в одной таблице через row_level.
COMMENT ON COLUMN spravki_port_stations.road IS 'Код дороги припортовой станции (ДВОСТ, ОКТ, СКАВ). Полное имя в road_codes.';
COMMENT ON COLUMN spravki_port_stations.station IS 'Название станции/терминала, либо строка-итог (ИТОГО ПО ПОРТАМ СЕТИ, ДАЛЬНЕВОСТОЧНАЯ …).';
COMMENT ON COLUMN spravki_port_stations.row_level IS 'Уровень строки: network=итог по сети, road=итог по дороге, port=станция, terminal=терминал, cargo=род груза. port/terminal/cargo входят в итоги network и road.';
COMMENT ON COLUMN spravki_port_stations.load_total IS 'Погрузка за сутки, вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.load_fact IS 'Фактическая выгрузка за сутки, вагон/сут. Коэффициент использования мощности = load_fact / capacity.';
COMMENT ON COLUMN spravki_port_stations.capacity IS 'Перерабатывающая способность, вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.wagons_total IS 'Наличие вагонов НАЗНАЧЕНИЕМ на припортовые станции по всей СЕТИ, факт (вагоны В ПУТИ к портам, НЕ на станции!). Норма — wagons_dest_net_norm.';
COMMENT ON COLUMN spravki_port_stations.wagons_road IS 'Наличие вагонов НАЗНАЧЕНИЕМ на припортовые станции на ДОРОГЕ назначения, факт. Норма — wagons_dest_road_norm.';
COMMENT ON COLUMN spravki_port_stations.wagons_dest_net_norm IS 'Наличие вагонов назначением→порты по СЕТИ, НОРМА.';
COMMENT ON COLUMN spravki_port_stations.wagons_dest_road_norm IS 'Наличие вагонов назначением→порты на ДОРОГЕ, НОРМА.';
COMMENT ON COLUMN spravki_port_stations.wagons_at_station_18 IS 'Наличие вагонов, фактически находящихся НА САМОЙ припортовой станции на 18:00. ЭТО ответ на «вагоны на припортовых станциях».';
COMMENT ON COLUMN spravki_port_stations.wagons_at_station_06 IS 'Наличие вагонов на самой станции на 06:00 следующих суток.';
COMMENT ON COLUMN spravki_port_stations.detained_trains IS 'Отставленные поезда (сеть, назначением→порты) на уровне данной строки.';
COMMENT ON COLUMN spravki_port_stations.detained_trains_road IS 'Отставленные поезда на дороге назначения.';
COMMENT ON COLUMN spravki_port_stations.load_total IS 'Погрузка за сутки, всего, вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.load_avg IS 'Погрузка средняя за период (ср/сут), вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.unload_avg IS 'Выгрузка средняя за период (ср/сут), вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.unload_06 IS 'Выгрузка на 06:00 следующих суток, вагон/сут.';
COMMENT ON COLUMN spravki_port_stations.unload_plan_next IS 'План выгрузки на 18:00 следующих суток, вагон/сут.';

-- ===================== spravki_speed =====================
-- Все скорости и отклонения — в км/ч.
COMMENT ON COLUMN spravki_speed.speed_type IS 'Тип скорости: section=участковая, technical=техническая. Обе в км/ч.';
COMMENT ON COLUMN spravki_speed.road IS 'Дорога. СЕТЬ — итог по всей сети. В секции technical — коды дорог (ОКТ, СВР …), в section — полные названия.';
COMMENT ON COLUMN spravki_speed.prev_year IS 'Скорость за аналогичный период прошлого года (нарастающим итогом с начала месяца), км/ч.';
COMMENT ON COLUMN spravki_speed.norm IS 'Норматив скорости, км/ч.';
COMMENT ON COLUMN spravki_speed.day_fact IS 'Факт за сутки, км/ч.';
COMMENT ON COLUMN spravki_speed.day_delta IS 'Отклонение day_fact от нормы, км/ч.';
COMMENT ON COLUMN spravki_speed.month_fact IS 'Факт с начала месяца (нарастающим итогом), км/ч.';
COMMENT ON COLUMN spravki_speed.month_delta IS 'Отклонение month_fact от нормы, км/ч.';
COMMENT ON COLUMN spravki_speed.year_delta IS 'Отклонение month_fact к прошлому году, км/ч. Отклонение считается от месячного факта (нарастающим итогом), не от суточного.';
COMMENT ON COLUMN spravki_speed.nopass_day_fact IS 'Без учёта пассажирского движения: факт за сутки, км/ч.';
COMMENT ON COLUMN spravki_speed.nopass_month_fact IS 'Без учёта пассажирского движения: факт с начала месяца, км/ч.';
COMMENT ON COLUMN spravki_speed.nopass_prev_year IS 'Без учёта пассажирского движения: прошлый год, км/ч.';
COMMENT ON COLUMN spravki_speed.nopass_year_delta IS 'Без учёта пассажирского движения: отклонение к прошлому году, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_day_fact IS 'Пассажирское движение: факт за сутки, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_month_fact IS 'Пассажирское движение: факт с начала месяца, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_prev_year IS 'Пассажирское движение: прошлый год, км/ч.';
COMMENT ON COLUMN spravki_speed.pass_year_delta IS 'Пассажирское движение: отклонение к прошлому году, км/ч.';

-- ===================== spravki_locomotives =====================
-- Эксплуатируемый парк локомотивов по тяговым полигонам и дорогам.
-- Два вида движения: грузовое (план/fact/delta) и все виды движения (plan_total/fact_total/delta_total).
COMMENT ON COLUMN spravki_locomotives.section IS 'Тип тяги: AC=переменный ток, DC=постоянный ток, diesel=тепловозы.';
COMMENT ON COLUMN spravki_locomotives.polygon IS 'Тяговый полигон. NULL — строка является итогом по полигону; road в ней = название полигона. Не-NULL — строка относится к дороге внутри этого полигона.';
COMMENT ON COLUMN spravki_locomotives.road IS 'В строках polygon IS NULL — название тягового полигона (итог по полигону). В строках polygon IS NOT NULL — код дороги внутри полигона (В-СИБ, ДВОСТ, ЗАБ …); полное имя в road_codes.';
COMMENT ON COLUMN spravki_locomotives.plan IS 'План парка в грузовом виде движения, ед. (операционный парк, по типу тяги).';
COMMENT ON COLUMN spravki_locomotives.fact IS 'Факт парка в грузовом виде движения, ед. (операционный парк, по типу тяги).';
COMMENT ON COLUMN spravki_locomotives.delta IS 'Отклонение fact − plan в грузовом виде движения, ед. Отрицательное — дефицит.';
COMMENT ON COLUMN spravki_locomotives.plan_total IS 'План парка по всем видам движения (грузовое + резерв + прочее), ед.';
COMMENT ON COLUMN spravki_locomotives.fact_total IS 'Факт парка по всем видам движения, ед.';
COMMENT ON COLUMN spravki_locomotives.delta_total IS 'Отклонение fact_total − plan_total, ед.';
COMMENT ON COLUMN spravki_locomotives.reserve IS 'Локомотивы в резерве, ед.';

-- ===================== spravki_sort_stations =====================
-- Важнейшие сортировочные станции.
COMMENT ON COLUMN spravki_sort_stations.road IS 'Код дороги станции.';
COMMENT ON COLUMN spravki_sort_stations.station IS 'Сортировочная станция (ЮДИНО, ДЕМА, ПЕРМЬ-СОРТ …).';
COMMENT ON COLUMN spravki_sort_stations.period IS 'Период (сут. — за сутки).';
COMMENT ON COLUMN spravki_sort_stations.working_park IS 'Рабочий парк вагонов на станции, факт, ед.';
COMMENT ON COLUMN spravki_sort_stations.park_norm IS 'Норматив рабочего парка, ед.';
COMMENT ON COLUMN spravki_sort_stations.rosp_total IS 'Расформировано вагонов с горки, всего, ед.';
COMMENT ON COLUMN spravki_sort_stations.rosp_no_pere IS 'Расформировано без переработки, ед.';
COMMENT ON COLUMN spravki_sort_stations.arrived_trains IS 'Прибыло поездов, ед.';
COMMENT ON COLUMN spravki_sort_stations.refused_trains IS 'Отклонено поездов, ед.';
COMMENT ON COLUMN spravki_sort_stations.formed_trains IS 'Сформировано составов, ед.';
COMMENT ON COLUMN spravki_sort_stations.sent_trains IS 'Отправлено поездов, ед.';
COMMENT ON COLUMN spravki_sort_stations.avg_weight IS 'Средний вес состава, т.';
COMMENT ON COLUMN spravki_sort_stations.avg_length IS 'Средняя длина состава, усл. ваг.';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_pere IS 'Простой транзитного вагона С ПЕРЕРАБОТКОЙ, факт, ч.';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_pere_norm IS 'Норматив простоя транзитного вагона С ПЕРЕРАБОТКОЙ, ч.';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_nopere IS 'Простой транзитного вагона БЕЗ ПЕРЕРАБОТКИ, факт, ч. (для вопроса «без переработки» — эти колонки, НЕ pere).';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_nopere_norm IS 'Норматив простоя транзитного вагона БЕЗ ПЕРЕРАБОТКИ, ч.';

-- ===================== spravki_speed_restrictions =====================
-- Ограничения скорости, не предусмотренные графиком движения поездов.
COMMENT ON COLUMN spravki_speed_restrictions.road IS 'Дорога. Итого по сети — строка-итог по всей сети.';
COMMENT ON COLUMN spravki_speed_restrictions.row_type IS 'Тип строки (fact — фактические ограничения).';
COMMENT ON COLUMN spravki_speed_restrictions.restrictions IS 'Количество ограничений скорости, ед.';
COMMENT ON COLUMN spravki_speed_restrictions.restrictions_km IS 'Протяжённость участков с ограничениями, км.';
COMMENT ON COLUMN spravki_speed_restrictions.ratio_pct IS 'Доля от развёрнутой длины, %.';
COMMENT ON COLUMN spravki_speed_restrictions.delta_km IS 'Изменение протяжённости ограничений к прошлому периоду, км.';
