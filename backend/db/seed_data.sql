-- ForgeSight — domain seed data (equipment + spares + work orders). Idempotent.
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
INSERT INTO spares (part_no, equipment_id, description, stock_qty, lead_time_days, supplier, unit_cost_inr) VALUES
  ('SKF-22230',      'sinter-fan-2',  'Spherical roller bearing 22230 CCK/W33', 1, 21, 'SKF', 285000),
  ('SKF-22230-F1',   'sinter-fan-1',  'Spherical roller bearing 22230 CCK/W33', 1, 21, 'SKF', 285000),
  ('ABB-BRES-8R2',   'hsm-f3-stand',  'ACS880 braking resistor assembly 8.2 ohm', 2, 7, 'ABB', 145000),
  ('CAST-MOLD-CU',   'caster-1',      'Copper mould plate set', 0, 45, 'Concast', 1200000),
  ('BF-STOVE-VALVE', 'bf-stove-a',    'Hot-blast stove changeover valve seal kit', 3, 14, 'Danieli', 95000),
  ('CRANE-BRK-PAD',  'ladle-crane-4', 'Crane hoist brake pad set', 4, 5, 'Konecranes', 42000)
ON CONFLICT (part_no) DO UPDATE
  SET stock_qty = EXCLUDED.stock_qty, lead_time_days = EXCLUDED.lead_time_days,
      unit_cost_inr = EXCLUDED.unit_cost_inr;

-- demo work orders (linked to at-risk assets) ---------------------------------------
INSERT INTO work_orders (id, equipment_id, title, description, status, priority, steps) VALUES
  ('a1000001-0000-4000-8000-000000000001', 'hsm-f3-stand', 'F3 VFD fault 0247 — braking resistor inspection',
   'Investigate ACS880 braking chopper fault 0247 after trip. Verify braking resistor continuity and cooling.',
   'open', 92,
   '[{"text":"LOTO F3 stand VFD panel","done":false,"safety":true},{"text":"Measure braking resistor ohms (expect 8.2 Ω ±5%)","done":false},{"text":"Inspect chopper IGBT thermal paste","done":false},{"text":"Restore and test at 10% speed","done":false}]'::jsonb),
  ('a1000001-0000-4000-8000-000000000002', 'sinter-fan-2', 'DE bearing vibration — bearing replacement prep',
   'DE bearing vibration trending above alarm. Plan bearing swap during Sunday shutdown window.',
   'in_progress', 78,
   '[{"text":"LOTO sinter ID fan #2","done":true,"safety":true},{"text":"Collect vibration baseline (DE + NDE)","done":true},{"text":"Verify SKF-22230 in stores","done":false},{"text":"Schedule crane + rigging for Sunday","done":false}]'::jsonb),
  ('a1000001-0000-4000-8000-000000000003', 'caster-1', 'Mould level sensor calibration',
   'Routine mould level sensor drift check — no immediate production risk.',
   'open', 45,
   '[{"text":"Verify mould level sensor zero","done":false},{"text":"Compare against tundish weight","done":false}]'::jsonb)
ON CONFLICT (id) DO UPDATE
  SET status = EXCLUDED.status, priority = EXCLUDED.priority, steps = EXCLUDED.steps,
      updated_at = now();
