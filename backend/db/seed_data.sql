-- ForgeSight — domain seed data (equipment + spares). Idempotent.
-- breakdown_history + sensor_readings + doc_chunks are loaded separately
-- (breakdown_history.json / sensor_readings.csv / corpus_ingest.sql) by apply_migrations.py.

-- 6 equipment (matches data/corpus/seed_corpus.py EQUIPMENT registry) -----------------
INSERT INTO equipment (id, name, zone, criticality, thresholds) VALUES
  ('hsm-f3-stand',  'Hot Strip Mill F3 Stand', 'Rolling', 9,
     '{"vibration_de": {"alarm": 6.0, "trip": 9.0}}'::jsonb),
  ('sinter-fan-2',  'Sinter Plant ID Fan #2',  'Sinter',  8,
     '{"vibration_de": {"alarm": 7.1, "trip": 11.0}}'::jsonb),
  ('caster-1',      'Continuous Caster #1',    'Casting', 10, '{}'::jsonb),
  ('bf-stove-a',    'Blast Furnace Stove A',   'Iron',    9,  '{}'::jsonb),
  ('ladle-crane-4', 'Ladle Crane #4',          'Casting', 7,  '{}'::jsonb),
  ('sinter-fan-1',  'Sinter Plant ID Fan #1',  'Sinter',  8,
     '{"vibration_de": {"alarm": 7.1, "trip": 11.0}}'::jsonb)
ON CONFLICT (id) DO UPDATE
  SET name = EXCLUDED.name, zone = EXCLUDED.zone,
      criticality = EXCLUDED.criticality, thresholds = EXCLUDED.thresholds;

-- spares (deliberately NOT embedded — volatile structured data, served by check_spares) -
INSERT INTO spares (part_no, equipment_id, description, stock_qty, lead_time_days, supplier) VALUES
  ('SKF-22230',      'sinter-fan-2',  'Spherical roller bearing 22230 CCK/W33', 1, 21, 'SKF'),
  ('SKF-22230-F1',   'sinter-fan-1',  'Spherical roller bearing 22230 CCK/W33', 1, 21, 'SKF'),
  ('ABB-BRES-8R2',   'hsm-f3-stand',  'ACS880 braking resistor assembly 8.2 ohm', 2, 7, 'ABB'),
  ('CAST-MOLD-CU',   'caster-1',      'Copper mould plate set', 0, 45, 'Concast'),
  ('BF-STOVE-VALVE', 'bf-stove-a',    'Hot-blast stove changeover valve seal kit', 3, 14, 'Danieli'),
  ('CRANE-BRK-PAD',  'ladle-crane-4', 'Crane hoist brake pad set', 4, 5, 'Konecranes')
ON CONFLICT (part_no) DO UPDATE
  SET stock_qty = EXCLUDED.stock_qty, lead_time_days = EXCLUDED.lead_time_days;
