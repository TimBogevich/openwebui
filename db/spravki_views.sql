-- spravki_views.sql — two trivial network-total views (the only logic we add).
-- After the 14.06.2026 analyst test, the two hardest double-count cases were the
-- network totals: delays (model got 950 instead of 475) and port detained trains.
-- These views pre-select the single correct ИТОГ row so a network-total question
-- physically cannot double-count. COMMENT ON VIEW first-sentence is surfaced by
-- describe() (mcp_postgres_server.py ~line 291-295), so the model discovers them.
-- Idempotent (CREATE OR REPLACE). No other views — per "minimal logic".
-- Apply: docker exec -i gcu-postgres psql -U postgres -d postgres < db/spravki_views.sql

-- Network total of detained trains: one pre-computed row per date.
CREATE OR REPLACE VIEW v_delays_total AS
SELECT report_date, trains, wagons
FROM spravki_delays
WHERE road_code = 'СЕТЬ' AND delay_code = 'ВСЕГО';
COMMENT ON VIEW v_delays_total IS 'Предвычисленный итог по сети по отставленным поездам. Один ряд на дату: trains = поездов, wagons = вагонов. Для вопроса «сколько всего отставлено по сети» — этот ряд.';

-- Network total for port stations: one pre-computed row per date.
CREATE OR REPLACE VIEW v_ports_network AS
SELECT report_date, load_fact, capacity, wagons_total, detained_trains
FROM spravki_port_stations
WHERE row_level = 'network';
COMMENT ON VIEW v_ports_network IS 'Предвычисленный итог по сети для припортовых станций. Один ряд на дату: load_fact = выгрузка, capacity = мощность, wagons_total = наличие, detained_trains = отставлено.';
