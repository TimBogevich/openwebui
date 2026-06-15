-- spravki_views.sql — two trivial network-total views (the only logic we add).
-- After the 14.06.2026 analyst test, the two hardest double-count cases were the
-- network totals: delays (model got 950 instead of 475) and port detained trains.
-- These views pre-select the single correct ИТОГ row so a network-total question
-- physically cannot double-count. COMMENT ON VIEW first-sentence is surfaced by
-- describe() (mcp_postgres_server.py ~line 291-295), so the model discovers them.
-- Idempotent (CREATE OR REPLACE). No other views — per "minimal logic".
-- Apply: docker exec -i gcu-postgres psql -U postgres -d postgres < db/spravki_views.sql

-- Network total of detained (отставленные) trains. Verified 12.03.2026 = 475 / 27 688.
CREATE OR REPLACE VIEW v_delays_total AS
SELECT report_date, trains, wagons
FROM spravki_delays
WHERE road_code = 'СЕТЬ' AND delay_code = 'ВСЕГО';
COMMENT ON VIEW v_delays_total IS 'Готовый ИТОГ по сети по отставленным (задержанным) поездам: поездов (trains) и вагонов (wagons) за дату — одна строка на дату для вопроса «сколько всего задержано/отставлено по сети».';

-- Network total for port stations. Verified 12.03.2026: detained_trains = 266.
CREATE OR REPLACE VIEW v_ports_network AS
SELECT report_date, load_fact, capacity, wagons_total, detained_trains
FROM spravki_port_stations
WHERE row_level = 'network';
COMMENT ON VIEW v_ports_network IS 'Готовый ИТОГ по сети по припортовым станциям: фактическая выгрузка (load_fact), перерабатывающая способность (capacity), наличие вагонов (wagons_total), отставленные поезда (detained_trains) — одна строка на дату для сетевых вопросов о работе портов.';
