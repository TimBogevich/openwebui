-- delay_codes_visibility.sql — add COLUMN comments to delay_reason_codes
-- so describe() shows what each column means, and tighten the routing
-- hint in spravki_delays comment to mention the JOIN target by name.
-- Apply: docker exec -i gcu-postgres psql -U postgres -d postgres < db/delay_codes_visibility.sql

COMMENT ON COLUMN delay_reason_codes.delay_code IS
  'Код причины задержки (текст: ''0''..''95''); ключ JOIN со spravki_delays.delay_code.';
COMMENT ON COLUMN delay_reason_codes.reason_name IS
  'Краткое название причины (как в spravki_delays.delay_name).';
COMMENT ON COLUMN delay_reason_codes.violation IS
  'Тип нарушения — короткая формулировка ситуации (например «Неприем вагонов грузополучателем»).';
COMMENT ON COLUMN delay_reason_codes.responsibility IS
  'Категория ответственности: Перевозчик (ответственность РЖД) / Грузоотправитель-Грузополучатель-Оператор ПС / Третьи лица-Сторонние организации.';
COMMENT ON COLUMN delay_reason_codes.units IS
  'Подразделение-нарушитель внутри ОАО РЖД (ЦД, ЦДИ, ЦТ, ЦТВР, ЦДРП, ТЭ, ЦМВПС, ЦДС, ЦСС, ЦФТО). Заполнено для responsibility=Перевозчик; для внешних причин — соответствующий внешний субъект (Грузополучатель, Грузоотправитель и т.п.).';
COMMENT ON COLUMN delay_reason_codes.source IS
  'Источник классификатора (методика №2040/р, Распоряжение №85/р 2025 г.).';
COMMENT ON COLUMN delay_reason_codes.note IS
  'Нейтральное пояснение особенностей кода (например: код 5 — платная услуга по договору, не влияет на срок доставки).';
COMMENT ON COLUMN delay_reason_codes.full_description IS
  'Полное официальное название причины из Распоряжения №85/р от 20.01.2025.';

-- Make spravki_delays comment mention the classifier by NAME (not just hint).
DO $$
DECLARE c text; marker text := 'JOIN delay_reason_codes';
BEGIN
  SELECT obj_description('spravki_delays'::regclass) INTO c;
  IF position(marker IN c) > 0 THEN
    RAISE NOTICE 'spravki_delays — уже содержит JOIN-подсказку';
  ELSE
    EXECUTE format(
      'COMMENT ON TABLE spravki_delays IS %L',
      c || ' Классификатор кодов (полные названия, ответственность, подразделение) — таблица delay_reason_codes, JOIN delay_reason_codes ON delay_code: responsibility=Перевозчик соответствует ответственности ОАО РЖД, иначе — внешние субъекты.'
    );
    RAISE NOTICE 'spravki_delays — JOIN-подсказка добавлена';
  END IF;
END$$;
