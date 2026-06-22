-- ============================================================================
-- Оперативные справки-источники к докладу ГЦУ
-- Идемпотентный. Данные сопоставляются с докладом ГЦУ через report_date.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- spravki_delays — Наличие задержанных поездов по кодам причин и дорогам
-- Источник: "Справка о наличии задержанных поездов.xlsx"
-- Связь с ГЦУ: report_date → показатели по задержкам/отставлению (раздел 6)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_delays (
    id            serial PRIMARY KEY,
    report_date   date NOT NULL,
    delay_code    varchar(10),           -- '0','1','2','4','5','6','21','22','24','43','44','92'
    delay_name    varchar(200),          -- 'Нет локомотива перевозчика' etc
    road_code     varchar(10) NOT NULL,  -- 'СЕТЬ','ОКТ','КЛГ','МСК',...
    trains        int,                   -- кол-во поездов (п-да)
    wagons        int                    -- кол-во вагонов (ваг)
);
CREATE INDEX IF NOT EXISTS idx_delays_date      ON spravki_delays (report_date);
CREATE INDEX IF NOT EXISTS idx_delays_code_date ON spravki_delays (delay_code, report_date);
COMMENT ON TABLE spravki_delays IS
  'Причины задержек/срыва сроков доставки: задержанные (отставленные) поезда по кодам причин и дорогам — для вопросов «почему/из-за чего не выполнен показатель доставки в срок». '
  'Источник справок к ГЦУ. Связывается с metrics по report_date. '
  'Коды: 0=без приказа,1=неприём грузопол,2=погран,4=др.вид тр-та,5=врем.размещение,'
  '6=ожид.накопл.суд.пар,21=отказ техсредств Т,22=нет лок-ва перевозч,'
  '24=нет лок-ва,43=отказ техсредств ДИ,44=несвоевр.очистка,92=угроза теракта. '
  'ВНИМАНИЕ ПРИ АГРЕГАЦИИ (иначе задвоишь): таблица уже содержит готовые итоги — '
  'НИКОГДА не суммируй trains/wagons по строкам. Итог по сети = ОДНА строка '
  'road_code=''СЕТЬ'' AND delay_code=''ВСЕГО''. Итог по одной дороге = ОДНА строка '
  'этой дороги с delay_code=''ВСЕГО''. Разрез по кодам в пределах сети = строки '
  'road_code=''СЕТЬ'' AND delay_code<>''ВСЕГО''. Всегда фиксируй ОДНО измерение '
  '(или дорогу, или код) и бери delay_code=''ВСЕГО'' для итоговой величины — не смешивай '
  'итоговую строку с детальными.';

-- ---------------------------------------------------------------------------
-- spravki_failures — Суточные отказы техсредств 1 и 2 категории
-- Источник: "Суточная оперативная справка о случаях отказов.xlsx"
-- Связь с ГЦУ: report_date → показатели отказов техсредств (раздел 5)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_failures (
    id            serial PRIMARY KEY,
    report_date   date NOT NULL,
    dept          varchar(200),   -- подразделение / дорога
    failures_2025 int,            -- кол-во отказов 2025
    failures_2026 int,            -- кол-во отказов 2026
    change_pct    numeric(8,2),   -- +/-% к 2025
    resolved      int,            -- устранено
    registered    int,            -- принято к учёту
    investigated  int,            -- расследовано
    duration_2025 numeric(10,2),  -- общая продолжительность отказов 2025, час
    duration_2026 numeric(10,2),  -- общая продолжительность отказов 2026, час
    duration_change_pct numeric(8,2), -- +/-% продолжительности к 2025
    freight_trains_delayed int,   -- задержано грузовых поездов из-за отказов, ед
    freight_train_hours numeric(10,2) -- продолжительность задержки грузовых, поездо-час
);
-- additive migration for existing DBs
ALTER TABLE spravki_failures ADD COLUMN IF NOT EXISTS duration_2025 numeric(10,2);
ALTER TABLE spravki_failures ADD COLUMN IF NOT EXISTS duration_2026 numeric(10,2);
ALTER TABLE spravki_failures ADD COLUMN IF NOT EXISTS duration_change_pct numeric(8,2);
ALTER TABLE spravki_failures ADD COLUMN IF NOT EXISTS freight_trains_delayed int;
ALTER TABLE spravki_failures ADD COLUMN IF NOT EXISTS freight_train_hours numeric(10,2);
ALTER TABLE spravki_failures ADD COLUMN IF NOT EXISTS section smallint;  -- 1=произошедшие на дороге, 2=по ответственности, 3=по комплексам
CREATE INDEX IF NOT EXISTS idx_failures_date ON spravki_failures (report_date);
COMMENT ON TABLE spravki_failures IS
  'Отказы техсредств 1-2 категории по подразделениям (дорогам и комплексам). '
  'failures_2026 — отказы за сутки, change_pct — % к 2025. '
  'ВНИМАНИЕ ПРИ АГРЕГАЦИИ: есть И детальные строки, И готовые итоги. Сетевой итог = '
  'строка dept ILIKE ''%Всего по сети%'' (НЕ суммируй подразделения — задвоишь). '
  'КРИТИЧНО — КОЛОНКА section: одна и та же дорога присутствует ДВАЖДЫ — в section=1 '
  '(отказы, ПРОИЗОШЕДШИЕ на территории дороги) и section=2 (отказы ПО ОТВЕТСТВЕННОСТИ '
  'подразделений дороги). Значения разные, но КАЖДЫЙ раздел уже суммируется в сетевой '
  'итог (234). НИКОГДА не складывай section 1 и 2 для одной дороги — это задвоит. '
  'Для разреза по дорогам бери ОДИН section (обычно section=1). section=3 — разбивка по '
  'хозкомплексам. Разрезы по комплексам — строки dept ILIKE ''%ВСЕГО по ... комплексу%'' '
  '(локомотивный/инфраструктурный/вагонный). '
  'ДВЕ РАЗНЫЕ МЕТРИКИ «ЧАСОВ» — НЕ ПУТАЙ: duration_2026 = длительность самих ОТКАЗОВ (ч); '
  'freight_train_hours = ЗАДЕРЖКА грузовых поездов (ПОЕЗДО-ЧАСЫ). Вопрос про «задержку '
  'поездов / поездо-часы» → freight_train_hours; про «продолжительность отказов» → duration_2026. '
  'Источник справок к ГЦУ. Связывается с metrics по report_date.';
COMMENT ON COLUMN spravki_failures.section IS
  '1 = отказы, произошедшие на территории дороги (Раздел 1); '
  '2 = отказы по ответственности подразделений дороги (Раздел 2); '
  '3 = разбивка по хозяйственным комплексам (Раздел 3). '
  'Каждый раздел независимо суммируется в сетевой ИТОГО — НЕ складывать разделы между собой.';

-- ---------------------------------------------------------------------------
-- spravki_locomotives — Эксплуатируемый парк локомотивов
-- Источник: "Справка Локомотивы.xlsx"
-- Связь с ГЦУ: report_date → показатели локомотивов (раздел 4)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_locomotives (
    id            serial PRIMARY KEY,
    report_date   date NOT NULL,
    section       varchar(100),   -- тип тяги: 'AC' (переменный ток), 'DC' (постоянный), 'diesel' (тепловозы)
    polygon       varchar(100),   -- 'Юго-Западный', 'Северо-Западный', 'Восточный', etc
    road          varchar(50),    -- дорога в составе полигона
    plan          int,            -- план в ГРУЗОВОМ движении
    fact          int,            -- факт в грузовом движении
    delta         int,            -- +/- грузовое
    plan_total    int,            -- план ВЕСЬ эксплуатируемый парк
    fact_total    int,            -- факт весь парк
    delta_total   int,            -- +/- весь парк
    reserve       int             -- Резерв
);
CREATE INDEX IF NOT EXISTS idx_loco_date ON spravki_locomotives (report_date);
ALTER TABLE spravki_locomotives ADD COLUMN IF NOT EXISTS plan_total int;
ALTER TABLE spravki_locomotives ADD COLUMN IF NOT EXISTS fact_total int;
ALTER TABLE spravki_locomotives ADD COLUMN IF NOT EXISTS delta_total int;
ALTER TABLE spravki_locomotives ADD COLUMN IF NOT EXISTS reserve int;
COMMENT ON TABLE spravki_locomotives IS
  'Эксплуатируемый парк локомотивов по полигонам/дорогам и ТИПАМ ТЯГИ (section: '
  'AC=переменный ток, DC=постоянный, diesel=тепловозы). '
  'ДВА УРОВНЯ СТРОК: (1) ИТОГ ПО ПОЛИГОНУ — polygon IS NULL, road = название полигона '
  '(Северо-Западный/Восточный/Юго-Западный/Московский/Октябрьский); (2) ДЕТАЛЬ ПО ДОРОГЕ — '
  'polygon = название полигона, road = код дороги внутри него. '
  'ДВЕ ПАРЫ ЧИСЕЛ — НЕ ПУТАЙ: plan/fact/DELTA = ГРУЗОВОЕ движение (для вопросов о '
  'недосодержании парка В ГРУЗОВОМ ДВИЖЕНИИ бери delta); plan_total/fact_total/delta_total = '
  'ВЕСЬ эксплуатируемый парк (грузовое+резерв+прочее) — НЕ для вопроса о недосодержании. '
  'РЕЦЕПТ «недосодержание по полигонам»: бери ТОЛЬКО строки-итоги (polygon IS NULL), '
  'суммируй delta по road (полигону): SELECT road, SUM(delta) FROM spravki_locomotives '
  'WHERE report_date=... AND polygon IS NULL GROUP BY road HAVING SUM(delta)<0. '
  'Это даёт верные С-Западный −171, Восточный −40 (НЕ −107: то ошибка от delta_total и от '
  'группировки по polygon, которая отбрасывает строки-итоги с polygon IS NULL). '
  'Каждый уровень имеет до 3 строк (по типу тяги). reserve — Резерв. Источник справок к ГЦУ '
  '(АРМ ОНД). Связывается с metrics по report_date.';

-- ---------------------------------------------------------------------------
-- spravki_port_stations — Работа припортовых станций
-- Источник: "Справка о работе припортовых станций на ДВС/ОКТ/СКАВ ж.д."
-- Связь с ГЦУ: report_date → показатели портов/выгрузки
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_port_stations (
    id            serial PRIMARY KEY,
    report_date   date NOT NULL,
    road          varchar(20),     -- 'ДВОСТ','ОКТ','СКАВ'
    station       varchar(200),
    row_level     varchar(10),     -- ИЕРАРХИЯ: network/road/port/terminal/cargo (из отступа)
    load_total    numeric(10,1),   -- ПОГРУЗКА всего за сутки (НЕ план выгрузки)
    load_fact     numeric(10,1),   -- ВЫГРУЗКА факт на 18:00
    capacity      numeric(10,1),   -- перерабатывающая способность (норма выгрузки)
    load_avg      numeric(10,1),   -- погрузка ср/сут
    unload_avg    numeric(10,1),   -- выгрузка ср/сут
    wagons_total  int,             -- наличие на СЕТИ назначением→порты, факт (НЕ на станции!)
    wagons_road   int,             -- наличие на ДОРОГЕ назначением→порты, факт
    detained_trains int,           -- отставленных поездов (сеть, назнач.→порты)
    detained_trains_road int,      -- отставленных поездов (на дороге назнач.)
    unload_plan_next numeric(10,1),-- план выгрузки на следующие сутки
    wagons_dest_net_norm  int,     -- наличие на СЕТИ назначением→порты, НОРМА
    wagons_dest_road_norm int,     -- наличие на ДОРОГЕ назначением→порты, НОРМА
    wagons_at_station_18  int,     -- наличие на САМОЙ СТАНЦИИ на 18:00 (это «вагоны на станции»)
    wagons_at_station_06  int,     -- наличие на САМОЙ СТАНЦИИ на 06:00 след. суток
    unload_06     numeric(10,1)    -- выгрузка на 06:00 след. суток
);
CREATE INDEX IF NOT EXISTS idx_ports_date ON spravki_port_stations (report_date);
-- additive migration for existing DBs (no-op if column already present)
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS capacity numeric(10,1);
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS row_level varchar(10);
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS load_avg numeric(10,1);
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS unload_avg numeric(10,1);
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS detained_trains_road int;
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS unload_plan_next numeric(10,1);
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS wagons_dest_net_norm int;
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS wagons_dest_road_norm int;
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS wagons_at_station_18 int;
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS wagons_at_station_06 int;
ALTER TABLE spravki_port_stations ADD COLUMN IF NOT EXISTS unload_06 numeric(10,1);
-- rename misnomer load_plan -> load_total (it was «погрузка всего», never a план выгрузки).
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='spravki_port_stations' AND column_name='load_plan') THEN
    ALTER TABLE spravki_port_stations RENAME COLUMN load_plan TO load_total;
  END IF;
END $$;
COMMENT ON TABLE spravki_port_stations IS
  'Работа припортовых станций: ВЫГРУЗКА факт (load_fact) против перерабатывающей способности (capacity), '
  'наличие вагонов, отставленные поезда — для вопросов об использовании перерабатывающей способности портов. '
  'КРИТИЧНО — ДВА РАЗНЫХ «НАЛИЧИЯ ВАГОНОВ», НЕ ПУТАЙ: '
  '(а) wagons_total / wagons_road = вагоны НАЗНАЧЕНИЕМ на припортовые станции (по всей СЕТИ / по ДОРОГЕ), '
  'это вагоны В ПУТИ к портам, а НЕ на самих станциях; '
  '(б) wagons_at_station_18 / wagons_at_station_06 = вагоны, фактически находящиеся НА САМОЙ СТАНЦИИ '
  '(на 18:00 и 06:00). Для вопроса «наличие вагонов НА припортовых станциях» бери wagons_at_station_18; '
  'для «наличие вагонов назначением НА порты / на сети» бери wagons_total. '
  'ВНИМАНИЕ ПРИ АГРЕГАЦИИ: есть И строки-станции, И готовые итоги (станция=''ИТОГО ПО ПОРТАМ СЕТИ'' '
  'и строки-дороги заглавными). Сетевой итог бери из строки ''ИТОГО ПО ПОРТАМ СЕТИ'' '
  '(НЕ суммируй станции — задвоишь с подитогами дорог). '
  'ВСЕГО 3 ПРИПОРТОВЫХ НАПРАВЛЕНИЯ (road): ДВОСТ, ОКТ, СКАВ. '
  'ПОЛНЫЙ ОТВЕТ на «проанализируй работу припортовых станций» ОБЯЗАН содержать: '
  '(1) сетевой итог — выгрузка факт (load_fact) против перерабатывающей способности (capacity) '
  'и КОЭФФИЦИЕНТ использования = load_fact/capacity (в процентах); '
  '(2) разрез по ВСЕМ 3 направлениям (ДВОСТ/ОКТ/СКАВ) — выгрузка/мощность/коэффициент по каждому; '
  '(3) ВЫВОД — какое направление хуже всех загружает мощность (минимальный коэффициент) и где наибольший резерв. '
  'Источник справок к ГЦУ. Связывается по report_date.';

-- ---------------------------------------------------------------------------
-- spravki_speed — Участковая и техническая скорость по дорогам
-- Источник: xlsb-файлы (участковая скорость + техническая скорость)
-- Связь с ГЦУ: report_date → показатели скорости
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_speed (
    id            serial PRIMARY KEY,
    report_date   date NOT NULL,
    speed_type    varchar(20) NOT NULL, -- 'section' (участковая) | 'technical' (техническая)
    road          varchar(100),
    prev_year     numeric(5,1),
    norm          numeric(5,1),
    day_fact      numeric(5,1),
    day_delta     numeric(5,1),        -- +/- к норме за сутки
    month_fact    numeric(5,1),
    month_delta   numeric(5,1),        -- +/- к норме нарастающим
    year_delta    numeric(5,1),        -- +/- к прошлому году
    -- участковая БЕЗ передаточных/вывозных поездов (только section):
    nopass_prev_year numeric(5,1),
    nopass_day_fact  numeric(5,1),
    nopass_month_fact numeric(5,1),
    nopass_year_delta numeric(5,1),
    -- участковая передаточных/вывозных поездов (только section):
    pass_prev_year   numeric(5,1),
    pass_day_fact    numeric(5,1),
    pass_month_fact  numeric(5,1),
    pass_year_delta  numeric(5,1)
);
CREATE INDEX IF NOT EXISTS idx_speed_date_type ON spravki_speed (report_date, speed_type);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS nopass_prev_year numeric(5,1);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS nopass_day_fact numeric(5,1);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS nopass_month_fact numeric(5,1);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS nopass_year_delta numeric(5,1);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS pass_prev_year numeric(5,1);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS pass_day_fact numeric(5,1);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS pass_month_fact numeric(5,1);
ALTER TABLE spravki_speed ADD COLUMN IF NOT EXISTS pass_year_delta numeric(5,1);
COMMENT ON TABLE spravki_speed IS
  'Участковая и техническая скорость по дорогам России. '
  'speed_type: section=участковая, technical=техническая. '
  'Источник справок к ГЦУ. Связывается по report_date.';

-- ---------------------------------------------------------------------------
-- spravki_speed_restrictions — Ограничения скорости, не предусмотренные графиком
-- Источник: "Справка об ограничениях скорости не предусмотренных графиком...xlsx"
-- В источнике данные хранятся как PNG-картинка внутри xlsx — числа извлечены
-- вручную из изображения в db/spravki_speed_restrictions_data.json.
-- Структура: одна строка = одна дорога × одна дата. Колонка row_type различает
-- плановое (заложено в график) и фактическое (в наличии) состояние.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_speed_restrictions (
    id              serial PRIMARY KEY,
    report_date     date NOT NULL,             -- 06.03 = plan baseline, 07–12.03 = facts
    road            varchar(50) NOT NULL,      -- название дороги или 'Итого по сети'
    row_type        varchar(10) NOT NULL,      -- 'plan' | 'fact'
    restrictions    int,                       -- кол-во ограничений, шт.
    restrictions_km numeric(10,1),             -- общая протяжённость, км
    ratio_pct       int,                       -- соотношение факта к плану, % (только для plan row, для контекста)
    delta_km        numeric(10,1)              -- отклонение в км (только для plan row, для контекста)
);
CREATE INDEX IF NOT EXISTS idx_speedrestr_date_road ON spravki_speed_restrictions (report_date, road);
COMMENT ON TABLE spravki_speed_restrictions IS
  'Ограничения скорости, не предусмотренные графиком движения поездов. '
  'По дорогам: количество ограничений (шт.) и общая протяжённость (км). '
  'row_type=plan — заложено в график, row_type=fact — фактическое в наличии. '
  'Источник — справка-картинка в xlsx, числа извлечены вручную.';

-- ---------------------------------------------------------------------------
-- spravki_sort_stations — Работа важнейших сортировочных станций
-- Источник: "Справка Анализ работы важнейших сортировочных станций сети ОАО РЖД.xlsb"
-- Структура: для каждой станции пара строк — суточный показатель и ср/сут.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_sort_stations (
    id              serial PRIMARY KEY,
    report_date     date NOT NULL,
    road            varchar(20),            -- ОКТ / МОСК / ГОРЬК / ...
    station         varchar(100) NOT NULL,  -- название станции (СПБ-СОРТ-МОС, ЮДИНО, ...)
    period          varchar(10) NOT NULL,   -- 'сут.' | 'ср/сут'
    working_park    numeric(10,1),          -- рабочий парк на 18:00
    rosp_total      numeric(10,1),          -- к роспуску всего
    arrived_trains  numeric(10,1),          -- прибыло поездов
    refused_trains  numeric(10,1),          -- расф. поездов
    rosp_no_pere    numeric(10,1),          -- к роспуску без пере
    formed_trains   numeric(10,1),          -- сформировано поездов
    sent_trains     numeric(10,1),          -- отправлено поездов
    avg_weight      numeric(10,1),          -- средний вес
    avg_length      numeric(10,1),          -- средняя условная длина
    park_norm       numeric(10,1),          -- рабочий парк НОРМАТИВ (план)
    idle_transit_pere      numeric(10,2),   -- простой транзитного вагона С ПЕРЕРАБОТКОЙ, факт (час)
    idle_transit_pere_norm numeric(10,2),   -- норма простоя транзит. вагона с переработкой (час)
    raw_extra       jsonb                   -- остальные числовые поля (для отладки)
);
CREATE INDEX IF NOT EXISTS idx_sortstan_date_road ON spravki_sort_stations (report_date, road);
-- additive migration for existing DBs
ALTER TABLE spravki_sort_stations ADD COLUMN IF NOT EXISTS park_norm numeric(10,1);
ALTER TABLE spravki_sort_stations ADD COLUMN IF NOT EXISTS idle_transit_pere numeric(10,2);
ALTER TABLE spravki_sort_stations ADD COLUMN IF NOT EXISTS idle_transit_pere_norm numeric(10,2);
ALTER TABLE spravki_sort_stations ADD COLUMN IF NOT EXISTS idle_transit_nopere numeric(10,2);       -- простой транзит. вагона БЕЗ переработки, факт (час)
ALTER TABLE spravki_sort_stations ADD COLUMN IF NOT EXISTS idle_transit_nopere_norm numeric(10,2);  -- норма простоя транзит. вагона без переработки (час)
COMMENT ON TABLE spravki_sort_stations IS
  'Работа важнейших сортировочных станций сети ОАО РЖД: рабочий парк, '
  'роспуск, расформирование, формирование, средний вес и длина состава. '
  'Перегруз/превышение нормативов: working_park (факт на 18:00) против park_norm '
  '(норматив). ДВА РАЗНЫХ ПРОСТОЯ — НЕ ПУТАЙ: '
  'idle_transit_pere / idle_transit_pere_norm = простой транзитного вагона С ПЕРЕРАБОТКОЙ '
  '(факт/норма, час); idle_transit_nopere / idle_transit_nopere_norm = простой транзитного '
  'вагона БЕЗ ПЕРЕРАБОТКИ (факт/норма, час). Для вопроса «с переработкой» бери pere-колонки, '
  '«без переработки» — nopere-колонки. Превышение = факт − норма (в ЧАСАХ); отклонение % = '
  '(факт−норма)/норма*100. Ранжирование «наибольшее превышение» — по АБСОЛЮТНОМУ превышению '
  'в часах (ORDER BY факт−норма DESC), процент приводится в скобках рядом; сортировка по часам '
  'и по процентам может давать РАЗНЫЙ порядок — для «топ-5 по превышению» используй ЧАСЫ. '
  'Бери строки period=''сут.''. '
  'period: сут.=за сутки, ср/сут=среднесуточно. Источник справок к ГЦУ.';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_nopere IS
  'Простой транзитного вагона БЕЗ переработки, ФАКТ (час). Источник: «Т без пер»/факт.';
COMMENT ON COLUMN spravki_sort_stations.idle_transit_nopere_norm IS
  'Норма простоя транзитного вагона БЕЗ переработки (час). Источник: «Т без пер»/норма.';

