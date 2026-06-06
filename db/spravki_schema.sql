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
  'Задержанные поезда по кодам причин и дорогам. '
  'Источник справок к ГЦУ. Связывается с metrics по report_date. '
  'Коды: 0=без приказа,1=неприём грузопол,2=погран,4=др.вид тр-та,5=врем.размещение,'
  '6=ожид.накопл.суд.пар,21=отказ техсредств Т,22=нет лок-ва перевозч,'
  '24=нет лок-ва,43=отказ техсредств ДИ,44=несвоевр.очистка,92=угроза теракта. '
  'ВСЕГО — итоговая строка по всем кодам.';

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
    investigated  int             -- расследовано
);
CREATE INDEX IF NOT EXISTS idx_failures_date ON spravki_failures (report_date);
COMMENT ON TABLE spravki_failures IS
  'Отказы техсредств 1-2 категории по подразделениям. '
  'Источник справок к ГЦУ. Связывается с metrics по report_date.';

-- ---------------------------------------------------------------------------
-- spravki_locomotives — Эксплуатируемый парк локомотивов
-- Источник: "Справка Локомотивы.xlsx"
-- Связь с ГЦУ: report_date → показатели локомотивов (раздел 4)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS spravki_locomotives (
    id            serial PRIMARY KEY,
    report_date   date NOT NULL,
    section       varchar(100),   -- 'AC' (переменный ток), 'DC' (постоянный), 'diesel'
    polygon       varchar(100),   -- 'Юго-Западный', 'Северо-Западный', 'Восточный', etc
    road          varchar(50),    -- дорога в составе полигона
    plan          int,
    fact          int,
    delta         int
);
CREATE INDEX IF NOT EXISTS idx_loco_date ON spravki_locomotives (report_date);
COMMENT ON TABLE spravki_locomotives IS
  'Эксплуатируемый парк локомотивов по полигонам и типам тяги. '
  'Источник справок к ГЦУ. Связывается с metrics по report_date.';

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
    load_plan     numeric(10,1),   -- погрузка норма
    load_fact     numeric(10,1),   -- погрузка факт
    wagons_total  int,             -- наличие вагонов всего
    wagons_road   int,             -- на дороге
    detained_trains int            -- отставленных поездов
);
CREATE INDEX IF NOT EXISTS idx_ports_date ON spravki_port_stations (report_date);
COMMENT ON TABLE spravki_port_stations IS
  'Работа припортовых станций: погрузка план/факт, наличие вагонов, отставленные поезда. '
  'Источник справок к ГЦУ. Дороги: ДВОСТ, ОКТ, СКАВ. Связывается по report_date.';

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
    year_delta    numeric(5,1)         -- +/- к прошлому году
);
CREATE INDEX IF NOT EXISTS idx_speed_date_type ON spravki_speed (report_date, speed_type);
COMMENT ON TABLE spravki_speed IS
  'Участковая и техническая скорость по дорогам России. '
  'speed_type: section=участковая, technical=техническая. '
  'Источник справок к ГЦУ. Связывается по report_date.';
